import argparse
import itertools
import json
import math
import os
import pandas as pd
from collections import defaultdict
from ortools.linear_solver import pywraplp

CODEBASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

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
        'recipe_name': objs[1],
        'machine': objs[2],
        'num_qual_modules': objs[3].split('-')[0],
        'num_prod_modules': objs[4].split('-')[0]
    }

def get_resource_item_key(item_key):
    return f'{item_key}-resource'

def get_resource_recipe_key(item_key):
    return f'{item_key}-mining'

def get_item_id(item_key, quality):
    return f'{QUALITY_NAMES[quality]}__{item_key}'

def get_input_id(item_id):
    return f'input__{item_id}'

def get_byproduct_id(item_id):
    return f'byproduct__{item_id}'

def get_output_id(item_id):
    return f'output__{item_id}'

class LinearSolver:

    def __init__(self, config, output_filename=None, verbose=False):
        self.output_filename = output_filename
        self.verbose = verbose

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

        with open(os.path.join(CODEBASE_PATH, config['data'])) as f:
            data = json.load(f)

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
                    if self.verbose:
                        print(f'IGNORING RECIPE {recipe_data["key"]}, {ingredient["name"]} NOT FOUND IN ITEMS LIST')
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
            prod_bonus = min(3.0, prod_bonus)
            speed_factor = crafting_machine_speed * (1 + self.building_speed_bonus) * (1 + \
                    + (num_effective_speed_modules * self.speed_module_bonus) \
                    - (num_qual_modules * self.speed_penalty_per_quality_module) \
                    - (num_prod_modules * self.speed_penalty_per_prod_module) \
            )

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
                self.solver_items[ingredient_item_id].append( (-1) * ingredient_amount_per_second_per_building * recipe_var)
                if self.verbose:
                    print(f'recipe {recipe_id} consumes {ingredient_amount_per_second_per_building} {ingredient_item_id}')
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

                    self.solver_items[result_item_id].append(result_amount_per_second_per_building * recipe_var)
                    if self.verbose:
                        print(f'recipe {recipe_id} produces {result_amount_per_second_per_building} {result_item_id}')

    def get_best_crafting_machine(self, recipe_data):
        recipe_category = recipe_data['category']
        allowed_crafting_machines = []
        for crafting_machine in self.crafting_machines.values():
            if self.crafting_machine_is_allowed(crafting_machine['key']) and (recipe_category in crafting_machine['crafting_categories']):
                allowed_crafting_machines.append(crafting_machine)

        # seems to only affect rocket-parts/rocket-silo, fix this later
        if len(allowed_crafting_machines)==0:
            if self.verbose:
                print(f'BAD RECIPE {recipe_data["key"]}, NO CRAFTING MACHINES FOUND')
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
            self.solver_items[item_id].append(solver_item_var)
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
            self.solver_items[item_id].append(-amount)
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
                        self.solver_items[byproduct_item_id].append( (-1.0) * solver_item_var)

        for item_id, solver_vars in self.solver_items.items():
            self.solver.Add(sum(solver_vars)==0)

        self.solver_costs.append(self.num_modules_var * self.module_cost)
        self.solver_costs.append(self.num_buildings_var * self.building_cost)
        self.solver.Minimize(sum(self.solver_costs))

        # Solve the system.
        print(f"Solving...")
        print('')
        status = self.solver.Solve()

        if status == pywraplp.Solver.OPTIMAL:
            print("Solution:")
            print(f"Objective value = {self.solver.Objective().Value()}")
            print('')
            print('Inputs used:')
            for input_var in self.solver_inputs.values():
                if input_var.solution_value() > 1e-9:
                    print(f'{input_var.name()}: {input_var.solution_value()}')
            print('')
            if self.allow_byproducts:
                print('Byproducts:')
                for byproduct_var in self.solver_byproducts.values():
                    if byproduct_var.solution_value() > 1e-9:
                        print(f'{byproduct_var.name()}: {byproduct_var.solution_value()}')
                print('')
            print(f'Buildings used: {self.num_buildings_var.solution_value()}')
            print('')
            print(f'Modules used: {self.num_modules_var.solution_value()}')
            print('')
            self.print_machine_layout()
            print('Recipes used:')
            for recipe_var in self.solver_recipes.values():
                if(recipe_var.solution_value()>1e-9):
                    print(f'{recipe_var.name()}: {recipe_var.solution_value()}')

            if self.output_filename is not None:
                print('')
                print(f'Writing output to: {self.output_filename}')
                recipe_data = []
                for recipe_var in self.solver_recipes.values():
                    if(recipe_var.solution_value()>1e-9):
                        curr_recipe_data = parse_recipe_id(recipe_var.name())
                        curr_recipe_data['num_buildings'] = recipe_var.solution_value()
                        recipe_data.append(curr_recipe_data)
                df = pd.DataFrame(columns=['recipe_name', 'recipe_quality', 'machine', 'num_qual_modules', 'num_prod_modules', 'num_buildings'], data=recipe_data)
                df.to_csv(self.output_filename, index=False)

        else:
            print("The problem does not have an optimal solution.")

    def print_machine_layout(self):
        variants = defaultdict(list)
        for recipe_var in self.solver_recipes.values():
            if(recipe_var.solution_value()>1e-9):
                data = parse_recipe_id(recipe_var.name())
                data['solution_value'] = recipe_var.solution_value()
                variants[data['recipe_name'], data['machine']].append(data)

        print("Machine layout:")

        for (name, machine), vars in variants.items():
            try:
                machine = self.items[machine]['localized_name']['en']
                name = self.recipes[name]['localized_name']['en']
            except KeyError:
                pass
            quals = []
            for var in vars:
                mods = ''
                if int(var['num_qual_modules']):
                    mods += f'{var["num_qual_modules"]}Q'
                if int(var['num_prod_modules']):
                    mods += f'{var["num_prod_modules"]}P'
                if mods:
                    mods = ' ' + mods
                quals.append(f"{var['recipe_quality']}{mods}")
            print(f'{name} in {machine}: {", ".join(quals)}')
        print()


def main():
    codebase_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    default_config_path = os.path.join(codebase_path, 'examples', 'electronic_circuits.json')

    parser = argparse.ArgumentParser(
        prog='Linear Solver',
        description='This program optimizes prod/qual ratios in factories in order to minimize inputs needed for a given output',
    )
    parser.add_argument('-c', '--config', type=str, default=default_config_path, help='Config file. Defaults to \'examples/one_step_example.json\'.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose mode. Prints out item and recipe information during setup.')
    parser.add_argument('-o', '--output', type=str, default=None, help='Output file')
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    solver = LinearSolver(config=config, output_filename=args.output, verbose=args.verbose)
    solver.run()

if __name__=='__main__':
    main()
