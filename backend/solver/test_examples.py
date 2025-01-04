import json
import os
import sys

CODEBASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(CODEBASE_PATH)

from solver.linear_solver import run_solver_from_command_line

def main():
    codebase_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    examples_path = os.path.join(codebase_path, 'examples')
    for example_config in os.listdir(examples_path):
        example_config_filename = os.path.join(examples_path, example_config)

        with open(example_config_filename ) as config_file:
            config = json.load(config_file)

        with open(config['data']) as data_file:
            data = json.load(data_file)

        run_solver_from_command_line(config, data)

if __name__=='__main__':
    main()
