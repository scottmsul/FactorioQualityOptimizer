'''
This script was written to solve the following problem.
Suppose we have a recipe A->B, and we start with basic quality A and want only legendary B.
We can do this by recycling any non-legendary B back into A.
We also assume this recipe can accept prod modules.
What are the optimal ratios of prod/quality in the assemblers, and what is the ratio of basic A to legendary B?

At a high level, we can solve a specific configuration by setting up a system of equations,
    then loop over all possible configurations to find the optimal configuration.
The system of equations is loosely based on this: https://kirkmcdonald.github.io/posts/calculation.html

We start by labeling each item i1, ..., iN, eg iron plate=i1, iron gear wheel=i2, etc.
A given recipe might be something like 2 iron plate -> 1 iron gear wheel, which would be 2i1 -> i2.
In general these look like a1*i1 + ... + aN*iN -> bi*i1 + ... + bN*iN (for most recipes, most an/bn are zero).
We can then construct a system of equations that balances the recipes in such a way to turn a given input into a given output.

As a simple example, suppose we wanted to know how many iron plates were needed for 1 iron gear.
Let #g be the number of output gears, #p be the number of input plates,
    and #R be a variable that represents how many buildings are needed for the (plate -> gear) recipe (assuming crafting speed 1)
We then have:

#R = 1 (each recipe building produces 1 gear)
#p = 2*#R  (each recipe building consumes 2 plates)

We can re-write in a more explicit way that states every variable in every equation:
1*#R + 0*#p = 1
-2*#R + 1*#p = 0

This can be abstracted as a matrix equation:
   -------
p: |-2  1|   |#R|   |0|
g: | 1  0| x |#p| = |1|
   -------

More generally we can setup any matrix problem as follows:
   ---------
i1:|R11 ... RM1  1  |   |#R1       |   |0   |
...|... ... ... (0s)| x |(#R2..#RM)| = |(0s)|
iN:|RN1 ... RNM  0  |   |#i1       |   |1   |

This matrix equation will solve for M=N-1 recipe buildings and some unknown #input i1 to generate 1 output of iN.
Once in matrix form, it can be solved quickly by numpy.

The code below represents i1-i5 as the five quality inputs, i6-i10 as the five quality outputs,
    and R1-R5 as the five different quality production recipes, and R6-R9 as the four different recycling recipes (we don't recycle legendary outputs).
#i1 is the main variable being solved (unknown # basic inputs) to generate 1 legendary output.

We use itertools to loop over all permutations of 0/4, 1/3, 2/2, 3/1, 4/0 in the first four production recipes to find the best one.
The last (legendary) production recipe is always prodded.
'''
import argparse
import itertools
import numpy as np

NUM_RECYCLING_MODULES = 4
RECYCLING_RATIO = 0.25

QUALITY_PROBABILITIES = [
    [.01, .013, .016, .019, .025],
    [.02, .026, .032, .038, .05],
    [.025, .032, .04, .047, .062]
]
PROD_BONUSES = [
    [.04, .05, .06, .07, 0.1],
    [.06, .07, .09, .11, .15],
    [.1, .13, .16, .19, .25]
]

class NoRecyclerSolver:

    def __init__(self, starting_quality, ending_quality, max_quality,\
            prod_module_bonus, quality_module_probability, enable_recycling, module_slots, additional_prod):
        self.starting_quality=starting_quality
        self.ending_quality=ending_quality
        self.max_quality=max_quality
        self.prod_module_bonus=prod_module_bonus
        self.quality_module_probability=quality_module_probability
        self.enable_recycling=enable_recycling
        self.module_slots=module_slots
        self.additional_prod=additional_prod

        self.max_quality_increase = max_quality - starting_quality
        self.end_quality_increase = ending_quality - starting_quality
        self.num_quality_items_in_solver = max_quality - starting_quality + 1
        self.num_quality_recipes_in_solver = ending_quality - starting_quality + 1
        self.num_extra_qualities = max_quality - ending_quality

    def initialize_recipe_matrix(self, frac_quality):
        frac_prod = 1-frac_quality
        q = self.module_slots * self.quality_module_probability * frac_quality
        p = 1 + self.module_slots * self.prod_module_bonus * frac_prod + self.additional_prod
        # setup recipe matrix
        X = np.zeros(self.num_quality_items_in_solver)

        X[0] = (1-q) * p

        for i in range(self.num_quality_items_in_solver-1):
            X[i] = 0.9 * 10**(-i+1) * q * p

        X[self.num_quality_items_in_solver-1] = 10**(-self.num_quality_items_in_solver+2) * q * p

        return X.reshape((self.num_quality_items_in_solver, 1))

    def solve(self, frac_quality):
        # convert to matrix for row reduction
        X = self.initialize_recipe_matrix(frac_quality)

        X_inputs = -np.ones((1, 1))
        recipes = np.block([
                [X_inputs],
                [X]
        ])

        input = np.zeros((self.num_quality_items_in_solver+1,1))
        input[0] = 1

        # every quality except the one of interest is a free item
        first_row = np.zeros((1, self.num_quality_items_in_solver))
        free_items = -np.identity(self.num_quality_items_in_solver)
        free_items = np.block([[first_row], [free_items]])
        free_items = np.delete(free_items, self.ending_quality-1, 1)

        eqs = np.block([[recipes, free_items, input]])

        goal = np.zeros(self.num_quality_items_in_solver+1)
        goal[-1-self.num_extra_qualities] = 1

        result = np.linalg.solve(eqs, goal)
        return result

    def optimize_modules(self):
        best_result = None
        best_num_input = 9999999
        possible_frac_qualities = np.linspace(1.0/self.module_slots, 1.0, num=self.module_slots)
        for frac_quality in possible_frac_qualities:
            result = self.solve(frac_quality)
            num_input = result[-1]
            if num_input < best_num_input:
                best_num_input = num_input
                best_frac_quality = frac_quality
                best_result = result
        return (best_frac_quality, best_result)
    
    def run(self):
        print('')
        print(f'optimizing production of output quality {self.ending_quality} from input quality {self.starting_quality}')
        print('')

        best_frac_quality, best_result = self.optimize_modules()
        best_num_input = best_result[-1]

        print(f'q{self.starting_quality} input per q{self.ending_quality} output: {best_num_input}')
        qual_modules = round(best_frac_quality*self.module_slots)
        prod_modules = round((1-best_frac_quality)*self.module_slots)
        print(f'optimal recipe uses {qual_modules} quality modules and {prod_modules} prod modules')
        print('')

        print(f'you also get the following byproducts for each q{self.ending_quality} output:')
        free_item_idx = 1
        for i in range(self.starting_quality, self.max_quality+1):
            if i != self.ending_quality:
                print(f'q{i} output: {best_result[free_item_idx]}')
                free_item_idx += 1

class RecyclerSolver:

    def __init__(self, starting_type, ending_type,starting_quality, ending_quality, max_quality,\
            prod_module_bonus, quality_module_probability, enable_recycling, module_slots, additional_prod, disable_prod):

        self.starting_type=starting_type.lower()
        self.ending_type=ending_type.lower()

        if(self.starting_type) not in ['ingredient', 'product']:
            raise ValueError('starting type must be either \'ingredient\' or \'product\'')
        if(self.ending_type) not in ['ingredient', 'product']:
            raise ValueError('ending type must be either \'ingredient\' or \'product\'')

        self.starting_quality=starting_quality
        self.ending_quality=ending_quality
        self.max_quality=max_quality
        self.prod_module_bonus=prod_module_bonus
        self.quality_module_probability=quality_module_probability
        self.enable_recycling=enable_recycling
        self.module_slots=module_slots
        self.additional_prod=additional_prod
        self.disable_prod=disable_prod

        self.max_quality_increase = max_quality - starting_quality
        self.end_quality_increase = ending_quality - starting_quality
        self.num_quality_items_in_solver = max_quality - starting_quality + 1
        self.num_quality_recipes_in_solver = ending_quality - starting_quality + 1
        self.num_extra_qualities = max_quality - ending_quality

        self.mat_size = 2*self.num_quality_items_in_solver

    def initialize_recipe_matrix(self, frac_quality):
        frac_prod = 1-frac_quality
        q = self.module_slots * self.quality_module_probability * frac_quality
        p = 1 + self.module_slots * self.prod_module_bonus * frac_prod + self.additional_prod
        # setup recipe matrix
        X = np.zeros((self.num_quality_recipes_in_solver, self.num_quality_items_in_solver))

        for i in range(self.num_quality_recipes_in_solver-1):
            X[i,i] = (1-q[i]) * p[i]

        for i in range(0, self.num_quality_recipes_in_solver-1):
            for j in range(i+1, self.num_quality_items_in_solver-1):
                X[i,j] = 0.9 * 10**(i-j+1) * q[i] * p[i]

        for i in range(self.num_quality_recipes_in_solver-1):
            X[i, self.num_quality_items_in_solver-1] = 10**(i-self.num_quality_items_in_solver+2) * q[i] * p[i]

        if self.disable_prod:
            X[self.num_quality_recipes_in_solver-1, self.num_quality_recipes_in_solver-1] = 1 + self.additional_prod
        else:           
            X[self.num_quality_recipes_in_solver-1, self.num_quality_recipes_in_solver-1] = 1 + self.module_slots * self.prod_module_bonus + self.additional_prod
        return X.T

    def initialize_recycling_matrix(self):
        # setup recycling matrix
        r = NUM_RECYCLING_MODULES * self.quality_module_probability
        R = np.zeros((self.num_quality_recipes_in_solver, self.num_quality_items_in_solver))

        for i in range(self.num_quality_recipes_in_solver-1):
            R[i, i] = (1-r)

        for i in range(0, self.num_quality_recipes_in_solver-1):
            for j in range(i+1, self.num_quality_items_in_solver-1):
                R[i,j] = 0.9 * 10**(i-j+1) * r

        for i in range(self.num_quality_recipes_in_solver-1):
            R[i, self.num_quality_items_in_solver-1] = 10**(i-self.num_quality_items_in_solver+2) * r

        R[self.num_quality_recipes_in_solver-1, self.num_quality_items_in_solver-1] = 1

        R *= RECYCLING_RATIO
        return R.T
    
    def initialize_input_matrix(self, num_cols):
        input = np.zeros((self.num_quality_items_in_solver, num_cols))
        for i in range(num_cols):
            input[i,i] = -1
        return input

    def solve(self, frac_quality):
        # convert to matrix for row reduction
        input = np.zeros((self.mat_size,1))

        if(self.starting_type=='ingredient'):
            input[0] = 1
        elif(self.starting_type=='product'):
            input[self.num_quality_items_in_solver] = 1

        X = self.initialize_recipe_matrix(frac_quality)
        R = self.initialize_recycling_matrix()
        X_inputs = self.initialize_input_matrix(self.num_quality_recipes_in_solver)
        R_inputs = self.initialize_input_matrix(self.num_quality_recipes_in_solver)

        if(self.ending_type=='ingredient'):
            X = X[:,:-1]
            X_inputs = X_inputs[:,:-1]
        elif(self.ending_type=='product'):
            R = R[:,:-1]
            R_inputs = R_inputs[:,:-1]

        recipes = np.block([
                [X_inputs, R],
                [X, R_inputs]
        ])

        free_items = np.zeros((self.num_quality_items_in_solver*2, self.num_extra_qualities*2))
        for i in range(self.num_extra_qualities):
            free_items[self.num_quality_recipes_in_solver+i, 2*i] = -1
            free_items[self.num_quality_items_in_solver+self.num_quality_recipes_in_solver+i, 2*i+1] = -1

        eqs = np.block([[recipes, free_items, input]])

        goal = np.zeros(self.mat_size)
        if(self.ending_type=='ingredient'):
            goal[self.num_quality_items_in_solver-1-self.num_extra_qualities] = 1
        if(self.ending_type=='product'):
            goal[-1-self.num_extra_qualities] = 1

        result = np.linalg.solve(eqs, goal)
        return result

    def optimize_modules(self):
        best_result = None
        best_num_input = 9999999
        possible_frac_qualities = np.linspace(0, 1.0, num=self.module_slots+1)
        for frac_quality in itertools.product(possible_frac_qualities, repeat=self.end_quality_increase):
            frac_quality = np.array(frac_quality)
            try:
                result = self.solve(frac_quality)
            except np.linalg.LinAlgError as e:
                continue
            num_input = result[-1]
            if num_input < best_num_input:
                best_num_input = num_input
                best_frac_quality = frac_quality
                best_result = result
        return (best_frac_quality, best_result)
    
    def run(self):
        print('')
        print(f'optimizing recycling loop that turns {self.starting_type} quality {self.starting_quality} into {self.ending_type} quality {self.ending_quality}')
        print('')

        best_frac_quality, best_result = self.optimize_modules()
        best_num_input = best_result[-1]

        # note that input/output qualities used start at 1 but the code starts at 0 for indexing
        print(f'q{self.starting_quality} input per q{self.ending_quality} output: {best_num_input}')
        for i in range(self.starting_quality, self.ending_quality):
            qual_modules = round(best_frac_quality[i-1-self.starting_quality]*self.module_slots)
            prod_modules = round((1-best_frac_quality[i-1-self.starting_quality])*self.module_slots)
            print(f'recipe q{i} uses {qual_modules} quality modules and {prod_modules} prod modules')
        if self.disable_prod:
            print(f'recipe q{self.ending_quality} uses 0 quality modules and 0 prod modules')
        else:
            print(f'recipe q{self.ending_quality} uses 0 quality modules and {self.module_slots} prod modules')

        if(self.num_extra_qualities > 0):
            print('')
            print(f'as an additional bonus you get the following for each q{self.ending_quality} output:')
            free_item_results = best_result[-(self.num_extra_qualities*2)-1:-1:]
            for i in range(self.num_extra_qualities):
                print(f'q{self.max_quality-self.num_extra_qualities+i+1} ingredient: {free_item_results[i*2]}')
                print(f'q{self.max_quality-self.num_extra_qualities+i+1} output: {free_item_results[i*2+1]}')

def main():
    parser = argparse.ArgumentParser(
        prog='Factorio Quality Optimizer',
        description='This program optimizes prod/qual ratios in factories, and calculates outputs for a given input',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('-st', '--starting-type', type=str, default='ingredient', help='Starting item type. String that is either \'ingredient\' or \'product\'. Ignored if --no-recycling flag is set, as starting type must be ingredient.')
    parser.add_argument('-et', '--ending-type', type=str, default='product', help='Ending item type. String that is either \'ingredient\' or \'product\'. Ignored if --no-recycling flag is set, as ending type must be product.')
    parser.add_argument('-pt', '--productivity-tier', type=int, default=3, help='Productivity module tier. Number from 1 to 3.')
    parser.add_argument('-qt', '--quality-tier', type=int, default=3, help='Quality module tier. Number from 1 to 3.')
    parser.add_argument('-q', '--module-quality', type=int, default=5, help='Quality of the modules in the assembler and recycler (if present). Number from 1 to 5.')
    parser.add_argument('-sq', '--starting-quality', type=int, default=1, help='Starting quality ingredient. Number from 1 to 4.')
    parser.add_argument('-eq', '--ending-quality', type=int, default=5, help='Ending quality to optimize. Number from 2 to 5. Must be greater than starting quality.')
    parser.add_argument('-mq', '--max-quality', type=int, default=5, help='Max quality unlocked. Number from 3 to 5. Must be greater than or equal to ending quality.')
    parser.add_argument('--enable-recycling', default=True, action=argparse.BooleanOptionalAction, help='Enables recycling loops. Set this flag if you have unlocked the recycler.')
    parser.add_argument('-ms', '--module-slots', type=int, default=4, help='number of module slots in the crafting building.')
    parser.add_argument('-p', '--additional-prod', type=float, default=0, help='any extra prod bonus, either from the building or recipe research. Units are percent out of 100. For example if using the foundry, enter 50.')
    parser.add_argument('--disable-prod', default=False, action=argparse.BooleanOptionalAction, help='Disables prod modules. Set this flag to calculate recipes that cannot use prod modules.')
    parser.set_defaults(enable_recycling=True)
    args = parser.parse_args()

    prod_module_bonus = PROD_BONUSES[args.productivity_tier-1][args.module_quality-1]
    quality_module_probability = QUALITY_PROBABILITIES[args.quality_tier-1][args.module_quality-1]

    if(args.disable_prod):
        prod_module_bonus = 0

    if(args.enable_recycling):
        solver = RecyclerSolver(
            starting_type=args.starting_type,
            ending_type=args.ending_type,
            starting_quality=args.starting_quality,
            ending_quality=args.ending_quality,
            max_quality=args.max_quality,
            prod_module_bonus=prod_module_bonus,
            quality_module_probability=quality_module_probability,
            enable_recycling=args.enable_recycling,
            module_slots=args.module_slots,
            additional_prod=args.additional_prod/100,
            disable_prod=args.disable_prod
        )
    else:
        solver = NoRecyclerSolver(
            starting_quality=args.starting_quality,
            ending_quality=args.ending_quality,
            max_quality=args.max_quality,
            prod_module_bonus=prod_module_bonus,
            quality_module_probability=quality_module_probability,
            enable_recycling=args.enable_recycling,
            module_slots=args.module_slots,
            additional_prod=args.additional_prod/100,
        )

    solver.run()

if __name__=='__main__':
    main()
