import argparse
import itertools
import json
import math
import os
import pandas as pd
import sys
from collections import defaultdict
from ortools.linear_solver import pywraplp

CODEBASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(CODEBASE_PATH)

import solver.flow_chart as fc

DEFAULT_RESOURCE_CATEGORY = 'basic-solid'

JUMP_QUALITY_PROBABILITY = 0.1
QUALITY_NAMES = ['normal', 'uncommon', 'rare', 'epic', 'legendary']
QUALITY_LEVELS = { quality_name: quality_level for quality_level, quality_name in enumerate(QUALITY_NAMES) }

QUALITY_PROBABILITIES = [
    [.01, .013, .016, .019, .025],
    [.02, .026, .032, .038, .05],
    [.025, .032, .04, .047, .062]
]

SPEED_PENALTIES_PER_QUALITY_MODULE = [0.05, 0.05, 0.05]

PROD_BONUSES = [
    [.04, .05, .06, .07, 0.1],
    [.06, .07, .09, .11, .15],
    [.1, .13, .16, .19, .25]
]

SPEED_PENALTIES_PER_PROD_MODULE = [0.05, 0.1, 0.15]

SPEED_BONUSES = [
    [0.2, 0.26, 0.32, 0.38, 0.5],
    [0.3, 0.39, 0.48, 0.57, 0.75],
    [0.5, 0.65, 0.8, 0.95, 1.25]
]

QUALITY_PENALTIES_PER_SPEED_MODULE = [.01, .015, .025]

# used for building crafting speed
QUALITY_BONUSES = [0.0, 0.3, 0.6, 0.9, 1.5]

# only check up to 8 beacons x 2 modules each
# set the number of beacons to ceil(num_modules/2)
POSSIBLE_NUM_BEACONED_SPEED_MODULES = list(range(17))

BEACON_EFFICIENCIES = [1.5, 1.7, 1.9, 2.1, 2.5]

MINIMUM_MODULE_SPEED_FACTOR = 0.2
MAXIMUM_PRODUCTIVITY_BONUS = 3.0

def calculate_num_effective_speed_modules(num_beaconed_speed_modules, beacon_efficiency):
    if num_beaconed_speed_modules == 0:
        return 0
    num_beacons = math.ceil(num_beaconed_speed_modules/2)
    return num_beaconed_speed_modules * beacon_efficiency * (num_beacons ** (-0.5))

def calculate_expected_amount(result_data, prod_bonus):
    # see here: https://lua-api.factorio.com/latest/types/ItemProductPrototype.html
    base_amount = result_data['amount'] if 'amount' in result_data.keys() \
        else 0.5 * (result_data['amount_min'] + result_data['amount_max'])
    probabiity_factor = result_data['probability'] if 'probability' in result_data.keys() else 1.0
    ignored_by_productivity = result_data['ignored_by_productivity'] if 'ignored_by_productivity' in result_data.keys() else 0.0
    extra_count_fraction = result_data['extra_count_fraction'] if 'extra_count_fraction' in result_data.keys() else 0.0

    base_amount_after_prod = ignored_by_productivity + (base_amount - ignored_by_productivity) * (1.0 + prod_bonus)
    amount_after_probabilities = base_amount_after_prod * probabiity_factor * (1.0 + extra_count_fraction)
    return amount_after_probabilities

def calculate_quality_probability_factor(starting_quality, ending_quality, max_quality_unlocked, quality_percent):
    if (starting_quality > max_quality_unlocked):
        raise ValueError('Starting quality cannot be above max quality unlocked')
    if(ending_quality > max_quality_unlocked):
        raise ValueError('Ending quality cannot be above max quality unlocked')
    if ending_quality < starting_quality:
        raise ValueError('Ending quality cannot be below starting quality')

    if  (ending_quality == starting_quality) and (starting_quality == max_quality_unlocked):
        # in this case there are no further qualities we can advance to, so quality remains the same with 100% probability.
        return 1

    elif ending_quality == starting_quality:
        # the probability that quality remains the same is (1 - probability-to-advance)
        return (1 - quality_percent)

    elif (ending_quality > starting_quality) and (ending_quality < max_quality_unlocked):
        # in this case we are producing a higher level quality with probability of quality_percent,
        # and jumped (ending_quality - starting_quality - 1) extra qualities with JUMP_QUALITY_PROBABILITY each time,
        # and the chance it doesn't advance further is 1-JUMP_QUALITY_PROBABILITY
        return quality_percent * (1-JUMP_QUALITY_PROBABILITY) * JUMP_QUALITY_PROBABILITY**(ending_quality - starting_quality - 1)

    elif (ending_quality > starting_quality) and (ending_quality == max_quality_unlocked):
        # this is the same case as above but without any probability of jumping further
        return quality_percent * JUMP_QUALITY_PROBABILITY**(ending_quality - starting_quality - 1)

    else:
        print(f'starting_quality: {starting_quality}')
        print(f'ending_quality: {starting_quality}')
        print(f'max_quality_unlocked: {max_quality_unlocked}')
        raise RuntimeError('Reached impossible condition in calculate_quality_probability_factor')

def get_recipe_id(recipe_key, quality, crafting_machine_key, num_qual_modules, num_prod_modules, num_beaconed_speed_modules):
    return f'{QUALITY_NAMES[quality]}__{recipe_key}__{crafting_machine_key}__{num_qual_modules}-qual__{num_prod_modules}-prod__{num_beaconed_speed_modules}-beaconed-speed'

def parse_recipe_id(recipe_id):
    objs = recipe_id.split('__')
    return {
        'recipe_quality': objs[0],
        'recipe_key': objs[1],
        'machine': objs[2],
        'num_qual_modules': int(objs[3].split('-')[0]),
        'num_prod_modules': int(objs[4].split('-')[0]),
        'num_beaconed_speed_modules': int(objs[5].split('-')[0])
    }

def get_resource_item_key(item_key):
    return f'{item_key}--resource'

def get_resource_recipe_key(item_key):
    return f'{item_key}--mining'

def parse_item_id(item_id):
    item_quality, item_key = item_id.split('__')
    return {
        'item_key': item_key,
        'item_quality': item_quality,
    }

def get_item_id(item_key, quality):
    return f'{QUALITY_NAMES[quality]}__{item_key}'

def get_input_id(item_id):
    return f'input__{item_id}'

def parse_input_id(input_id):
    _, item_quality, item_key = input_id.split('__')
    return {
        'item_key': item_key,
        'item_quality': item_quality,
    }

def get_byproduct_id(item_id):
    return f'byproduct__{item_id}'

def parse_byproduct_id(byproduct_id):
    _, item_quality, item_key = byproduct_id.split('__')
    return {
        'item_key': item_key,
        'item_quality': item_quality,
    }

def get_output_id(item_id):
    return f'output__{item_id}'

def format_float(f):
    if f >= 1.0:
        return '{:.2f}'.format(f)
    elif f >= 0.1:
        return '{:.3f}'.format(f)
    elif f >= 0.01:
        return '{:.4f}'.format(f)
    else:
        return '{:.2e}'.format(f) # scientific notation for small numbers

class LinearSolver:

    def __init__(self, config, data, output_filename=None, output_flow_chart=None):
        self.output_filename = output_filename
        self.output_flow_chart = output_flow_chart

        quality_module_tier = config['quality_module_tier']
        quality_module_quality_level = QUALITY_LEVELS[config['quality_module_quality']]
        self.quality_module_probability = QUALITY_PROBABILITIES[quality_module_tier-1][quality_module_quality_level]

        prod_module_tier = config['prod_module_tier']
        prod_module_quality_level = QUALITY_LEVELS[config['prod_module_quality']]
        self.prod_module_bonus = PROD_BONUSES[prod_module_tier-1][prod_module_quality_level]

        speed_module_tier = config['speed_module_tier']
        speed_module_quality_level = QUALITY_LEVELS[config['speed_module_quality']]
        self.speed_module_bonus = SPEED_BONUSES[speed_module_tier-1][speed_module_quality_level]

        check_speed_modules = config['check_speed_modules'] if 'check_speed_modules' in config else None
        self.possible_num_beaconed_speed_modules = POSSIBLE_NUM_BEACONED_SPEED_MODULES if check_speed_modules else [0]

        self.speed_penalty_per_quality_module = SPEED_PENALTIES_PER_QUALITY_MODULE[quality_module_tier-1]
        self.speed_penalty_per_prod_module = SPEED_PENALTIES_PER_PROD_MODULE[prod_module_tier-1]
        self.quality_penalty_per_speed_module = QUALITY_PENALTIES_PER_SPEED_MODULE[speed_module_tier-1]

        building_quality = QUALITY_LEVELS[config['building_quality']]
        self.building_speed_bonus = QUALITY_BONUSES[building_quality]
        self.beacon_efficiency = BEACON_EFFICIENCIES[building_quality]

        self.productivity_research = config['productivity_research'] if 'productivity_research' in config else {}

        self.allow_byproducts = config['allow_byproducts'] if 'allow_byproducts' in config  else None

        self.allowed_recipes = config['allowed_recipes'] if 'allowed_recipes' in config else None
        self.disallowed_recipes = config['disallowed_recipes'] if 'disallowed_recipes' in config else None

        self.allowed_crafting_machines = config['allowed_crafting_machines'] if 'allowed_crafting_machines' in config else None
        self.disallowed_crafting_machines = config['disallowed_crafting_machines'] if 'disallowed_crafting_machines' in config else None

        self.max_quality_unlocked = QUALITY_LEVELS[config['max_quality_unlocked']]
        self.building_cost = config['building_cost']
        self.module_cost = config['module_cost']
        self.inputs = config['inputs']
        self.outputs = config['outputs']

        self.resources = { resource_data['key']: resource_data for resource_data in data['resources'] }
        self.mining_drills = { mining_drill_data['key']: mining_drill_data for mining_drill_data in data['mining_drills'] }
        self.items = { item_data['key']: item_data for item_data in data['items']}
        self.crafting_machines = { crafting_machine_data['key']: crafting_machine_data for crafting_machine_data in data['crafting_machines'] }
        self.recipes = { recipe_data['key']: recipe_data for recipe_data in data['recipes']}

        for item_key, item_data in self.items.items():
            item_allows_quality = item_data['type'] != 'fluid'
            item_data['allows_quality'] = item_allows_quality
            item_data['qualities'] = list(range(self.max_quality_unlocked+1)) if item_allows_quality else [0]

        # don't loop the list itself since we delete elements from it
        recipe_keys = list(self.recipes.keys())
        for recipe_key in recipe_keys:
            # note that some recipes have no ingredients
            recipe_allows_quality = False
            recipe_data = self.recipes[recipe_key]
            for ingredient in recipe_data['ingredients']:
                if ingredient['name'] not in self.items.keys():
                    # there are a handful of "nonsense-recipes" in the data file with items that don't exist (red wire recycling, etc)
                    del self.recipes[recipe_key]
                else:
                    if self.items[ingredient['name']]['allows_quality']:
                        recipe_allows_quality = True
            recipe_data['allows_quality'] = recipe_allows_quality
            recipe_data['qualities'] = list(range(self.max_quality_unlocked+1)) if recipe_allows_quality else [0]

        # keys are '{quality_name}__{item_name}', values are lists of solver variables
        # mostly [(recipe)*(amount)]'s) that get summed to a constraint (i.e. zero)
        self.solver_items = {}
        # keys are are '{quality_name}__{recipe_name}__{num_qual_modules}-qual__{num_prod_modules}-prod'
        # each quality level of crafting, and each separate combination of qual/prod, is a separate allowable recipe
        # solved result is equivalent to number of buildings in units where craft_time=1 and craft_speed=1
        self.solver_recipes = {}
        self.solver_inputs = {}
        self.solver_byproducts = {}
        self.solver_outputs = {}
        self.num_modules_var = None
        self.num_buildings_var = None
        self.solver_costs = []
        self.solver = pywraplp.Solver.CreateSolver("GLOP")
        if not self.solver:
            raise RuntimeError('error setting up solver')

    def validate_productivity_research(self):
        for recipe_key in self.productivity_research.keys():
            # assume the recipe name is the same as the item name
            if recipe_key not in self.recipes.keys():
                raise RuntimeError(f'No recipe found for productivity research item {recipe_key}')

    def recipe_is_allowed(self, recipe_key):
        if (self.allowed_recipes is not None) and (self.disallowed_recipes is not None):
            raise RuntimeError('Illegal configuration. Cannot set both allowed_recipes and disallowed_recipes.')
        if self.allowed_recipes is not None:
            return (recipe_key in self.allowed_recipes)
        elif self.disallowed_recipes is not None:
            return (recipe_key not in self.disallowed_recipes)
        else:
            return True

    def crafting_machine_is_allowed(self, crafting_machine_key):
        if (self.allowed_crafting_machines is not None) and (self.disallowed_crafting_machines is not None):
            raise RuntimeError('Illegal configuration. Cannot set both allowed_crafting_machines and disallowed_crafting_machines.')
        if self.allowed_crafting_machines is not None:
            return (crafting_machine_key in self.allowed_crafting_machines)
        elif self.disallowed_crafting_machines is not None:
            return (crafting_machine_key not in self.disallowed_crafting_machines)
        else:
            return True

    def setup_resource(self, resource_data):
        item_key = resource_data['key']
        resource_item_key = get_resource_item_key(item_key)
        resource_recipe_key = get_resource_recipe_key(item_key)
        ingredients = [{ 'name': resource_item_key, 'amount': 1 }]
        if 'required_fluid' in resource_data.keys():
            ingredients.append({ 'name': resource_data['required_fluid'], 'amount': resource_data['fluid_amount'] })
        mock_item_data = {
            'key': resource_item_key,
            'allows_quality': False,
            'qualities': [0],
        }
        mock_recipe_data = {
            'key': resource_recipe_key,
            # technically productivity modules can be used in mining to reduce resource drain
            # in practice I don't think I would care about this and instead prefer qual modules
            'allow_productivity': False,
            'ingredients': ingredients,
            'results': resource_data['results'],
            'energy_required': resource_data['mining_time'],
            'category': resource_data['category'] if 'category' in resource_data.keys() else DEFAULT_RESOURCE_CATEGORY,
            'allows_quality': False,
            'qualities': [0]
        }
        self.items[resource_item_key] = mock_item_data
        self.recipes[resource_recipe_key] = mock_recipe_data

    def setup_mining_drill(self, mining_drill_data):
        key = mining_drill_data['key']
        mock_crafting_machine_data = {
            'key': key,
            'module_slots': mining_drill_data['module_slots'],
            'crafting_speed': mining_drill_data['mining_speed'],
            'crafting_categories': mining_drill_data['resource_categories'],
            # technically big mining drills have less resource drain (and an effective resource prod bonus)
            # but I don't see this is in the json file.
            # I think this is unlikely to affect overall results (i.e. prod/qual ratios)
            # would only affect cost function of "xxx-ore-resource"
            'prod_bonus': 0.0
        }
        self.crafting_machines[key] = mock_crafting_machine_data

    def setup_item(self, item_data):
        item_key = item_data['key']
        for quality in item_data['qualities']:
            item_id = get_item_id(item_key, quality)
            self.solver_items[item_id] = []

    def setup_recipe_var(self, recipe_data, crafting_machine_data):
        recipe_key = recipe_data['key']
        allow_productivity = recipe_data['allow_productivity']
        ingredients = recipe_data['ingredients']
        results = recipe_data['results']
        energy_required = recipe_data['energy_required']

        crafting_machine_key = crafting_machine_data['key']
        crafting_machine_speed = crafting_machine_data['crafting_speed']
        crafting_machine_module_slots = crafting_machine_data['module_slots']
        crafting_machine_prod_bonus = crafting_machine_data['prod_bonus']

        recipe_qualities = recipe_data['qualities']
        num_possible_qual_modules = list(range(crafting_machine_module_slots+1))

        productivity_research = 0 if recipe_key not in self.productivity_research.keys() else self.productivity_research[recipe_key]

        for recipe_quality, num_qual_modules, num_beaconed_speed_modules in itertools.product(recipe_qualities, num_possible_qual_modules, self.possible_num_beaconed_speed_modules):
            if allow_productivity:
                num_prod_modules = crafting_machine_module_slots - num_qual_modules
            else:
                num_prod_modules = 0
            # TODO: maybe speed modules in beacons should cost less since they can be spread across multiple assemblers
            num_modules = num_qual_modules + num_prod_modules + num_beaconed_speed_modules

            num_effective_speed_modules = calculate_num_effective_speed_modules(num_beaconed_speed_modules, self.beacon_efficiency)
            quality_penalty_from_speed_modules = num_effective_speed_modules * self.quality_penalty_per_speed_module

            prod_bonus = num_prod_modules * self.prod_module_bonus + crafting_machine_prod_bonus + productivity_research
            prod_bonus = min(MAXIMUM_PRODUCTIVITY_BONUS, prod_bonus)

            module_speed_factor = 1 + \
                    + (num_effective_speed_modules * self.speed_module_bonus) \
                    - (num_qual_modules * self.speed_penalty_per_quality_module) \
                    - (num_prod_modules * self.speed_penalty_per_prod_module)
            module_speed_factor = max(MINIMUM_MODULE_SPEED_FACTOR, module_speed_factor)
            speed_factor = crafting_machine_speed * (1 + self.building_speed_bonus) * module_speed_factor

            # we want recipe_var to represent the number of buildings when all is finished
            # that way (recipe_var * module_cost) accurately represents the number of modules used per recipe
            recipe_id = get_recipe_id(recipe_key=recipe_key, quality=recipe_quality, crafting_machine_key=crafting_machine_key, num_prod_modules=num_prod_modules, num_qual_modules=num_qual_modules, num_beaconed_speed_modules=num_beaconed_speed_modules)
            recipe_var = self.solver.NumVar(0, self.solver.infinity(), name=recipe_id)
            self.solver_recipes[recipe_id] = recipe_var
            if num_modules > 0:
                self.num_modules_var += num_modules * recipe_var
            self.num_buildings_var += recipe_var

            for ingredient in ingredients:
                ingredient_item_data = self.items[ingredient['name']]
                ingredient_quality = recipe_quality if ingredient_item_data['allows_quality'] else 0
                ingredient_item_id = get_item_id(ingredient['name'], ingredient_quality)
                # ingredient quality is same as recipe quality

                ingredient_amount_per_second_per_building = ingredient['amount'] * speed_factor / energy_required

                # negative because it is consumed
                self.solver_items[ingredient_item_id].append({
                    'var': recipe_var,
                    'amount': (-1) * ingredient_amount_per_second_per_building
                })
            # ingredient qualities can produce all possible higher qualities
            for result_data in results:
                result_item_data = self.items[result_data['name']]
                result_qualities = result_item_data['qualities']
                if result_item_data['allows_quality']:
                    result_qualities = [quality for quality in result_qualities if quality >= recipe_quality]

                for result_quality in result_qualities:
                    result_item_id = get_item_id(result_data['name'], result_quality)

                    expected_amount = calculate_expected_amount(result_data, prod_bonus)

                    if result_item_data['allows_quality']:
                        quality_percent = num_qual_modules * self.quality_module_probability - num_effective_speed_modules * self.quality_penalty_per_speed_module
                        quality_percent = max(quality_percent, 0)
                        quality_probability_factor = calculate_quality_probability_factor(recipe_quality, result_quality, self.max_quality_unlocked, quality_percent)
                    else:
                        quality_probability_factor = 1.0
                    result_amount_per_second_per_building = expected_amount * speed_factor * quality_probability_factor / energy_required

                    self.solver_items[result_item_id].append({
                        'var': recipe_var,
                        'amount': result_amount_per_second_per_building
                    })

    def get_best_crafting_machine(self, recipe_data):
        recipe_category = recipe_data['category']
        allowed_crafting_machines = []
        for crafting_machine in self.crafting_machines.values():
            if self.crafting_machine_is_allowed(crafting_machine['key']) and (recipe_category in crafting_machine['crafting_categories']):
                allowed_crafting_machines.append(crafting_machine)

        # seems to only affect rocket-parts/rocket-silo, fix this later
        if len(allowed_crafting_machines)==0:
            return None

        max_module_slots = max(c['module_slots'] for c in allowed_crafting_machines)
        max_prod_bonus = max(c['prod_bonus'] for c in allowed_crafting_machines)
        max_crafting_speed = max(c['crafting_speed'] for c in allowed_crafting_machines)
        best_crafting_machine = [c for c in allowed_crafting_machines if \
                (c['module_slots'] == max_module_slots) and \
                (c['prod_bonus'] == max_prod_bonus) and \
                (c['crafting_speed'] == max_crafting_speed)]
        if len(best_crafting_machine) != 1:
            raise RuntimeError('Unable to disambiguate best crafting machine')
        return best_crafting_machine[0]

    def run(self):
        self.validate_productivity_research()

        self.num_modules_var = self.solver.NumVar(0, self.solver.infinity(), name='num-modules')
        self.num_buildings_var = self.solver.NumVar(0, self.solver.infinity(), name='num-buildings')

        for resource_data in self.resources.values():
            self.setup_resource(resource_data)

        for mining_drill_data in self.mining_drills.values():
            self.setup_mining_drill(mining_drill_data)

        # needs to happen first as setup_recipe depends on self.items being initialized
        for item_data in self.items.values():
            self.setup_item(item_data)

        for recipe_data in self.recipes.values():
            recipe_key = recipe_data['key']
            if self.recipe_is_allowed(recipe_key):
                crafting_machine_data = self.get_best_crafting_machine(recipe_data)
                if crafting_machine_data is not None:
                    self.setup_recipe_var(recipe_data, crafting_machine_data)

        # needed to help determine byproducts
        solver_input_item_ids = []
        for input in self.inputs:
            # Create variable for free production of input
            if input['resource']:
                input_item_key = get_resource_item_key(input['key'])
            else:
                input_item_key = input['key']
            input_quality = QUALITY_LEVELS[input['quality']]
            item_id = get_item_id(input_item_key, input_quality)
            cost = input['cost']
            input_id = get_input_id(item_id)
            solver_item_var = self.solver.NumVar(0, self.solver.infinity(), name=input_id)
            self.solver_inputs[item_id] = solver_item_var
            self.solver_items[item_id].append({
                'var': solver_item_var,
                'amount': 1.0
            })
            self.solver_costs.append(cost * solver_item_var)
            solver_input_item_ids.append(item_id)

        # needed to help determine byproducts
        solver_output_item_ids = []
        for output in self.outputs:
            output_item_key = output['key']
            output_quality = QUALITY_LEVELS[output['quality']]
            item_id = get_item_id(output_item_key, output_quality)
            amount = output['amount']
            output_id = get_output_id(item_id)
            self.solver_items[item_id].append({
                'var': None,
                'amount': -amount
            })
            solver_output_item_ids.append(item_id)

        if self.allow_byproducts:
            for item_data in self.items.values():
                byproduct_item_key = item_data['key']
                byproduct_qualities = item_data['qualities']
                for byproduct_quality in byproduct_qualities:
                    byproduct_item_id = get_item_id(byproduct_item_key, byproduct_quality)
                    if (byproduct_item_id not in solver_input_item_ids) and (byproduct_item_id not in solver_output_item_ids):
                        # Create variable for free consumption of byproduct
                        byproduct_id = get_byproduct_id(byproduct_item_id)
                        solver_item_var = self.solver.NumVar(0, self.solver.infinity(), name=byproduct_id)
                        self.solver_byproducts[byproduct_item_id] = solver_item_var
                        self.solver_items[byproduct_item_id].append({
                            'var': solver_item_var,
                            'amount': -1.0
                        })

        for item_id, solver_vars in self.solver_items.items():
            constraint = []
            for factor in solver_vars:
                if factor['var'] is None:
                    constraint.append(factor['amount'])
                else:
                    constraint.append(factor['var'] * factor['amount'])
            self.solver.Add(sum(constraint)==0)

        self.solver_costs.append(self.num_modules_var * self.module_cost)
        self.solver_costs.append(self.num_buildings_var * self.building_cost)
        self.solver.Minimize(sum(self.solver_costs))

        status = self.solver.Solve()

        results = {}

        if status == pywraplp.Solver.OPTIMAL:
            results['solved'] = True

            results['cost'] = self.solver.Objective().Value()
            results['num_buildings'] = self.num_buildings_var.solution_value()
            results['num_modules'] = self.num_modules_var.solution_value()

            results['input_items'] = defaultdict(dict)
            results['input_resources'] = {}
            for input_var in self.solver_inputs.values():
                if input_var.solution_value() > 1e-9:
                    input_info = parse_input_id(input_var.name())
                    raw_item_key = input_info['item_key']
                    if raw_item_key.endswith('--resource'):
                        factorio_item_key = raw_item_key.split('--')[0]
                        results['input_resources'][factorio_item_key] = input_var.solution_value()
                    else:
                        factorio_item_key = raw_item_key
                        results['input_items'][factorio_item_key][input_info['item_quality']] = input_var.solution_value()

            if self.allow_byproducts:
                results['byproducts'] = defaultdict(dict)
                for byproduct_var in self.solver_byproducts.values():
                    if byproduct_var.solution_value() > 1e-9:
                        byproduct_info = parse_byproduct_id(byproduct_var.name())
                        results['byproducts'][byproduct_info['item_key']][byproduct_info['item_quality']] = byproduct_var.solution_value()

            results['mining_recipes'] = defaultdict(list)
            results['crafting_recipes'] = defaultdict(lambda: defaultdict(list))
            for recipe_var in self.solver_recipes.values():
                if(recipe_var.solution_value()>1e-9):
                    recipe_info = parse_recipe_id(recipe_var.name())
                    raw_recipe_key = recipe_info['recipe_key']
                    num_buildings = recipe_var.solution_value()

                    if raw_recipe_key.endswith('--mining'):
                        factorio_recipe_key = raw_recipe_key.split('--')[0]
                    else:
                        factorio_recipe_key = raw_recipe_key

                    # this part is tricky so I'll add a detailed explanation below
                    # recall the definition of self.solver_items:
                    #   - keys are '{quality_name}__{item_name}'
                    #   - values are lists of { 'var': solver_variable, 'amount': float }
                    # in this context:
                    #   - 'var' points to the ortools variable that represents the number of buildings for a given recipe
                    #   - 'amount' is how much each unit of that recipe is affected by the solver_items key
                    # to get the ingredients/products that are consumed/produced by a recipe, we do the following:
                    #   - loop over everything in self.solver_items
                    #   - check if any of its associated variables match the current recipe_var
                    #   - if so, multiply its amount by the recipe's solved num_buildings and add it to the ingredients/products entry
                    resource_consumption = None
                    ingredients = defaultdict(dict)
                    products = defaultdict(dict)
                    for item_id, solver_var_infos in self.solver_items.items():
                        item_info = parse_item_id(item_id)
                        raw_item_key = item_info['item_key']
                        if raw_item_key.endswith('--resource'):
                            factorio_item_key = raw_item_key.split('--')[0]
                        else:
                            factorio_item_key = raw_item_key
                        for solver_var_info in solver_var_infos:
                            if recipe_var is solver_var_info['var']:
                                amount_per_recipe = solver_var_info['amount']
                                total_amount = amount_per_recipe * num_buildings
                                # note that total_amount can equal zero in some cases (i.e. in quality recipe with no quality modules)
                                if total_amount < 0:
                                    if raw_recipe_key.endswith('--mining'):
                                        if factorio_item_key == factorio_recipe_key:
                                            resource_consumption = (-1) * amount
                                        else:
                                            ingredients[factorio_item_key] = (-1) * total_amount
                                    else:
                                        ingredients[factorio_item_key][item_info['item_quality']] = (-1) * total_amount
                                elif total_amount > 0:
                                    products[item_info['item_key']][item_info['item_quality']] = total_amount

                    if raw_recipe_key.endswith('--mining'):
                        results['mining_recipes'][factorio_recipe_key].append({
                            'num_buildings': recipe_var.solution_value(),
                            'machine': recipe_info['machine'],
                            'num_prod_modules': recipe_info['num_prod_modules'],
                            'num_qual_modules': recipe_info['num_qual_modules'],
                            'num_beaconed_speed_modules': recipe_info['num_beaconed_speed_modules'],
                            'resource_consumption': resource_consumption,
                            'ingredients': ingredients,
                            'products': products
                        })
                    else:
                        results['crafting_recipes'][factorio_recipe_key][recipe_info['recipe_quality']].append({
                            'num_buildings': recipe_var.solution_value(),
                            'machine': recipe_info['machine'],
                            'num_prod_modules': recipe_info['num_prod_modules'],
                            'num_qual_modules': recipe_info['num_qual_modules'],
                            'num_beaconed_speed_modules': recipe_info['num_beaconed_speed_modules'],
                            'ingredients': ingredients,
                            'products': products
                        })

        else:
            results['solved'] = False

        return results

def print_results(results, data, verbose):
    if not results['solved']:
        print("The problem does not have an optimal solution.")
        return

    # config file test examples don't have 'localized_name' entries, just display the key if 'localized_name' not present
    item_names = {}
    for item_data in data['items']:
        item_names[item_data['key']] = item_data['localized_name']['en'].lower() if 'localized_name' in item_data else item_data['key']

    recipe_names = {}
    for recipe_data in data['recipes']:
        recipe_names[recipe_data['key']] = recipe_data['localized_name']['en'].lower() if 'localized_name' in recipe_data else recipe_data['key']

    print("Solution:")
    print(f"Objective value = {results['cost']}")

    print('')
    print(f"Buildings used: {results['num_buildings']}")
    print(f"Modules used: {results['num_modules']}")

    print('')
    print('Input Resources:')
    for item_key, amount in results['input_resources'].items():
        print(f'{item_key} (resource): {format_float(amount)}')

    print('Input Items:')
    for item_key, outer_value in results['input_items'].items():
        for item_quality, amount in outer_value.items():
            print(f'{item_quality} {item_key}: {format_float(amount)}')

    if 'byproducts' in results:
        print('')
        print('Byproducts:')
        for item_key, outer_value in results['byproducts'].items():
            for item_quality, amount in outer_value.items():
                print(f'{item_quality} {item_key}: {format_float(amount)}')

    print('')
    print('Mining Recipes:')
    import pprint
    pprint.pprint(results['mining_recipes'])
    for recipe_key, recipe_infos in results['mining_recipes'].items():
        for recipe_info in recipe_infos:
            machine_key = recipe_info['machine']
            # test examples don't have crafting machine name entries
            machine_name = item_names[machine_key] if machine_key in item_names else machine_key
            description = []
            q = recipe_info['num_qual_modules']
            p = recipe_info['num_prod_modules']
            bs = recipe_info['num_beaconed_speed_modules']
            num_buildings = recipe_info['num_buildings']
            resource_consumption = recipe_info['resource_consumption']
            if q > 0:
                description.append(f'{q}Q')
            if p > 0:
                description.append(f'{p}P')
            if bs > 0:
                description.append(f'{bs}BS')
            description.extend([item_names[recipe_key], 'mining', 'in', f'{machine_name}:', format_float(num_buildings)])
            print(' '.join(description))
            if verbose:
                print(f'Resource Consumption: {format_float(resource_consumption)}')
                print('    Ingredients:')
                for ingredient_item_key, ingredient_infos in recipe_info['ingredients'].items():
                    for ingredient_item_quality, ingredient_amount in ingredient_infos.items():
                        ingredient_name = item_names[ingredient_item_key]
                        print(f"        {ingredient_item_quality} {ingredient_item_key}: {format_float(ingredient_amount)}")
                print('    Products:')
                for product_item_key, product_infos in recipe_info['products'].items():
                    for product_item_quality, product_amount in product_infos.items():
                        product_name = item_names[product_item_key]
                        print(f"        {product_item_quality} {product_item_key}: {format_float(product_amount)}")


    print('')
    print('Crafting Recipes:')
    for recipe_key, outer_value in results['crafting_recipes'].items():
        for recipe_quality, recipe_infos in outer_value.items():
            for recipe_info in recipe_infos:
                machine_key = recipe_info['machine']
                # test examples don't have crafting machine name entries
                machine_name = item_names[machine_key] if machine_key in item_names else machine_key
                description = []
                q = recipe_info['num_qual_modules']
                p = recipe_info['num_prod_modules']
                bs = recipe_info['num_beaconed_speed_modules']
                num_buildings = recipe_info['num_buildings']
                if q > 0:
                    description.append(f'{q}Q')
                if p > 0:
                    description.append(f'{p}P')
                if bs > 0:
                    description.append(f'{bs}BS')
                description.extend([recipe_quality, recipe_names[recipe_key], 'in', f'{machine_name}:', format_float(num_buildings)])
                print(' '.join(description))
                if verbose:
                    print('    Ingredients:')
                    for ingredient_item_key, ingredient_infos in recipe_info['ingredients'].items():
                        for ingredient_item_quality, ingredient_amount in ingredient_infos.items():
                            ingredient_name = item_names[ingredient_item_key]
                            print(f"        {ingredient_item_quality} {ingredient_item_key}: {format_float(ingredient_amount)}")
                    print('    Products:')
                    for product_item_key, product_infos in recipe_info['products'].items():
                        for product_item_quality, product_amount in product_infos.items():
                            product_name = item_names[product_item_key]
                            print(f"        {product_item_quality} {product_item_key}: {format_float(product_amount)}")

def output_to_csv(results, data, output_csv):
    item_names = { item_data['key']: item_data['localized_name']['en'].lower() for item_data in data['items']}
    recipe_names = { recipe_data['key']: recipe_data['localized_name']['en'].lower() for recipe_data in data['recipes']}
    print('')
    print(f'Writing crafting recipes to: {output_csv}')
    recipe_data = []
    for recipe_key, outer_value in results['crafting_recipes'].items():
        for recipe_quality, recipe_infos in outer_value.items():
            for recipe_info in recipe_infos:
                curr_recipe_data = {
                    'recipe_name': recipe_names[recipe_key],
                    'recipe_quality': recipe_quality,
                    'machine': item_names[recipe_info['machine']],
                    'num_qual_modules': recipe_info['num_qual_modules'],
                    'num_prod_modules': recipe_info['num_prod_modules'],
                    'num_beaconed_speed_modules': recipe_info['num_beaconed_speed_modules'],
                    'num_buildings': recipe_info['num_buildings'],
                }
                recipe_data.append(curr_recipe_data)
    df = pd.DataFrame(columns=['recipe_name', 'recipe_quality', 'machine', 'num_qual_modules', 'num_prod_modules', 'num_beaconed_speed_modules', 'num_buildings'], data=recipe_data)
    df.to_csv(output_csv, index=False)

# shared by factorio_solver and linear_solver __main__ threads
def run_solver_from_command_line(config, data, verbose=False, output_csv=None, output_flow_chart=None):
    solver = LinearSolver(config=config, data=data)
    results = solver.run()

    print_results(results, data, verbose)

    if output_csv is not None:
        output_to_csv(results, data, output_csv)

    if output_flow_chart is not None:
        fc.FlowChartGenerator(solver.solver_recipes, solver.recipes, solver.items, verbose).write_flow_chart(output_flow_chart)

def main():
    codebase_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    default_config_path = os.path.join(codebase_path, 'examples', 'electronic_circuits.json')

    parser = argparse.ArgumentParser(
        prog='Linear Solver',
        description='This program optimizes prod/qual ratios in factories in order to minimize inputs needed for a given output',
    )
    parser.add_argument('-c', '--config', type=str, default=default_config_path, help='Config file. Defaults to \'examples/one_step_example.json\'.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose mode. Prints input and output amounts for each solved recipe.')
    parser.add_argument('-o', '--output-csv', type=str, default=None, help='Output recipes to csv file')
    parser.add_argument('-of', '--output-flow-chart', type=str, default=None, help='Output recipes to flow chart html file')
    args = parser.parse_args()

    with open(args.config) as config_file:
        config = json.load(config_file)

    with open(config['data']) as data_file:
        data = json.load(data_file)

    run_solver_from_command_line(config, data, args.verbose, args.output_csv, args.output_flow_chart)

if __name__=='__main__':
    main()
