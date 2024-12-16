from flask import Flask, render_template, request

import os
import sys
ROOT_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(ROOT_PATH)

import solver.factorio_solver as fs
import solver.linear_solver as ls

app = Flask(__name__)


@app.route('/', methods=['GET'])
def index_get():
    return render_template('index.html')

@app.route('/results', methods=['GET'])
def index_post(): # run solver using post params
    allowed_recipes = None
    disallowed_recipes = None
    if request.args.get('filter_input_recipes'):
        if request.args['input_recipes_type'] == 'allowed':
            allowed_recipes = request.args['input_recipes'].split(' ')
        elif request.args['input_recipes_type'] == 'disallowed':
            disallowed_recipes = request.args['input_recipes'].split(' ')

    allowed_crafting_machines = None
    disallowed_crafting_machines = None
    if request.args.get('filter_input_crafting_machines'):
        if request.args['input_crafting_machines_type'] == 'allowed':
            allowed_crafting_machines = request.args['input_crafting_machines'].split(' ')
        elif request.args['input_crafting_machines_type'] == 'disallowed':
            disallowed_crafting_machines = request.args['input_crafting_machines'].split(' ')

    inputs = []
    if request.args['input_items'] != '':
        input_items = fs.parse_input_list(request.args['input_items'].split(' '), request.args['input_quality'])
        inputs.extend(input_items)
    if request.args['input_resources'] != '':
        input_resources = fs.parse_resources_list(request.args['input_resources'].split(' '))
        inputs.extend(input_resources)

    productivity_research = fs.parse_productivity_research_list(request.args['productivity_research']) if request.args['productivity_research']!='' else {}

    config = {
        "data": fs.FACTORIO_DATA_FILENAME,
        "quality_module_tier": int(request.args['quality_module_tier']),
        "quality_module_quality": request.args['quality_module_quality'],
        "prod_module_tier": int(request.args['prod_module_tier']),
        "prod_module_quality": request.args['prod_module_quality'],
        "check_speed_modules": bool(request.args.get('check_speed_modules')),
        "speed_module_tier": int(request.args['speed_module_tier']),
        "speed_module_quality": request.args['speed_module_quality'],
        "building_quality": request.args['building_quality'],
        "max_quality_unlocked": request.args['max_quality_unlocked'],
        "productivity_research": productivity_research,
        "allow_byproducts": bool(request.args.get('allow_byproducts')),
        "module_cost": float(request.args['module_cost']),
        "building_cost": float(request.args['building_cost']),
        "allowed_recipes": allowed_recipes,
        "disallowed_recipes": disallowed_recipes,
        "allowed_crafting_machines": allowed_crafting_machines,
        "disallowed_crafting_machines": disallowed_crafting_machines,
        "inputs": inputs,
        "outputs": [
            {
                "key": request.args['output_item'],
                "quality": request.args['output_quality'],
                "amount": float(request.args['output_amount']),
            },
        ],
    }

    solver = ls.LinearSolver(config=config, data=fs.FACTORIO_DATA)
    results = solver.run()
    return render_template('results.html', results=results)
