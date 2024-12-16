# Factorio Quality Optimizer

The latest expansion to Factorio introduced [Quality](https://factorio.com/blog/post/fff-375), a new mechanic in which quality modules can be used to increase the quality of every item in the game.
However, producing higher tiers of quality is exponentially difficult, as the probability of increasing quality by even one tier is quite small, let alone trying to make Legendary.
One way to automate the crafting of higher-tier quality items is to recycle lower-quality items that are below the desired tier, as demonstrated in the original quality FFF that only retains rare and above:

![alt text](fff-375-quality-recycling.jpg)

## Intro to Optimization

What does it mean to optimize a quality recycling loop?
Intuitively, one might think this always means maximizing high-quality-output per low-quality input.
That was my first thought, and indeed many others' as well.
The script will let you run optimization problems phrased in this way, if that's what you want.
For instance, we can craft legendary outputs from normal inputs using t3 legendary modules and four modules slots.
For an output-amount of 0.5 gears from iron plates (accounting for 2 gears per plate), we get 79.9 normal inputs per legendary output using 2 prod/2 qual at each stage, a result that's familiar for those who have looked into quality loops:

```
python ./solver/factorio_solver.py --input-items iron-plate=1 --output-item iron-gear-wheel --output-amount 0.5 --input-resources --allowed-recipes iron-gear-wheel iron-gear-wheel-recycling --module-cost 0
Solving...

Solution:
Objective value = 79.87855759632305

Inputs used:
input__normal__iron-plate: 79.87855759632305

Modules used: 28.117711868628877

Recipes used:
normal__iron-gear-wheel__assembling-machine-3__2-qual__2-prod: 15.154990004569166
uncommon__iron-gear-wheel__assembling-machine-3__2-qual__2-prod: 2.1091570618602837
rare__iron-gear-wheel__assembling-machine-3__2-qual__2-prod: 0.6924569930969829
epic__iron-gear-wheel__assembling-machine-3__2-qual__2-prod: 0.21058218706088602
legendary__iron-gear-wheel__assembling-machine-3__0-qual__4-prod: 0.036779441875883084
normal__iron-gear-wheel-recycling__recycler__4-qual__0-prod: 7.2601873990639145
uncommon__iron-gear-wheel-recycling__recycler__4-qual__0-prod: 1.9353460386638042
rare__iron-gear-wheel-recycling__recycler__4-qual__0-prod: 0.5529474685588199
epic__iron-gear-wheel-recycling__recycler__4-qual__0-prod: 0.16526527387913567
```

However, this isn't always necessarily what we "want". 
For instance, setting up normal iron plates might be cheaper than making legendary t3 modules.
What if instead of optimizing output per input, we optimized for fewest modules needed to make 1 output/sec?
We can answer this question by changing the cost function, specifically by setting the cost of modules to 1 and the cost of resources to 0:

```
python ./solver/factorio_solver.py --input-items iron-plate=0 --output-item iron-gear-wheel --output-amount 0.5 --input-resources --allowed-recipes iron-gear-wheel iron-gear-wheel-recycling --module-cost 1
Solving...

Solution:
Objective value = 27.117698734433013

Inputs used:
input__normal__iron-plate: 84.15177514007344

Modules used: 27.11769873443301

Recipes used:
normal__iron-gear-wheel__assembling-machine-3__3-qual__1-prod: 16.008738539929865
uncommon__iron-gear-wheel__assembling-machine-3__2-qual__2-prod: 1.8975330026119661
rare__iron-gear-wheel__assembling-machine-3__2-qual__2-prod: 0.6843506941231083
epic__iron-gear-wheel__assembling-machine-3__2-qual__2-prod: 0.21026892285287516
legendary__iron-gear-wheel__assembling-machine-3__0-qual__4-prod: 0.03676426976614069
normal__iron-gear-wheel-recycling__recycler__4-qual__0-prod: 5.514468464503185
uncommon__iron-gear-wheel-recycling__recycler__4-qual__0-prod: 2.0430934408670294
rare__iron-gear-wheel-recycling__recycler__4-qual__0-prod: 0.5570612191493366
epic__iron-gear-wheel-recycling__recycler__4-qual__0-prod: 0.165420180629505
```

Note the solution is very similar, except it switches to 3 qual / 1 prod from 2 qual / 2 prod on the normal recipe.
In this case we only needed 27.1 modules instead of 28.1, at the cost of using 84.1 plates/sec instead of 79.9.
Both results are similar to each other, but that might not always be the case.

By default, the script sets the cost functions to 1 for each raw resource/sec and 1 for each module.
This doesn't mean they are "balanced", just that they are both used.
It is your responsibility to understand the cost function and how to set it for what you want.

Incidentally, if we allow every recipe in the game, the best way to make legendary gears from normal plates uses underground transport belts!
This is true even when optimizing purely for outputs/input.
```
python ./solver/factorio_solver.py --input-items iron-plate=1 --output-item iron-gear-wheel --output-amount 0.5 --input-resources --module-cost 0
Solving...

Solution:
Objective value = 47.92572353617703

Inputs used:
input__normal__iron-plate: 47.92572353617703

Modules used: 6.697192928380107

Recipes used:
normal__iron-gear-wheel__assembling-machine-3__1-qual__3-prod: 1.1567933649742508
rare__iron-gear-wheel__assembling-machine-3__1-qual__3-prod: 0.14537129486887093
epic__iron-gear-wheel__assembling-machine-3__2-qual__2-prod: 0.16455992900591462
legendary__iron-gear-wheel__assembling-machine-3__0-qual__4-prod: 0.03719143286847192
epic__iron-gear-wheel-recycling__recycler__4-qual__0-prod: 0.11927776088383932
normal__transport-belt__foundry__4-qual__0-prod: 0.7417485580489188
uncommon__transport-belt__foundry__4-qual__0-prod: 0.11788605433844081
rare__transport-belt__foundry__4-qual__0-prod: 0.1796263454021076
uncommon__transport-belt-recycling__recycler__4-qual__0-prod: 0.7846884433871048
rare__transport-belt-recycling__recycler__4-qual__0-prod: 0.6394397818845146
epic__transport-belt-recycling__recycler__4-qual__0-prod: 0.15348133953442797
legendary__transport-belt-recycling__recycler__0-qual__0-prod: 0.021913551047174205
normal__underground-belt__foundry__4-qual__0-prod: 0.8495028768622637
uncommon__underground-belt__foundry__4-qual__0-prod: 0.12452081339248364
normal__underground-belt-recycling__recycler__4-qual__0-prod: 0.9582392451006334
uncommon__underground-belt-recycling__recycler__4-qual__0-prod: 0.4248730406802073
rare__underground-belt-recycling__recycler__4-qual__0-prod: 0.07013092464115211
epic__underground-belt-recycling__recycler__4-qual__0-prod: 0.007013092464115212
legendary__underground-belt-recycling__recycler__0-qual__0-prod: 0.0009350789952153614
```

Speculating here, but this could be because the legendary t3 the probability is weighted more for one quality jump (24%) than for skipping qualities (10%) and therefore wants as many "one-quality-jump" opportunities as possible, which means having more production stages.

## Web App

Currently this app being updated to have a web-based UI that uses localhost web servers.
The final result will likely involve two servers, a back-end API that uses Flask, and a front-end that uses React.
At the moment there is only a Flask server.
To run, use the following command:

`flask --app ./backend/flask_app.py run --debug`

After launching, open `127.0.0.1:5000` in a browser, or the url displayed by Flask if different.

Currently it's a very basic UI with no css, and is more of a proof-of-concept than a final version.

Note that if you have a web development background and are interested in improving the Flask-based UI, I'll most likely accept improvements, but note that any work on the Flask side might become irrelevant if I implement a separate front-end.

## Overview of the Scripts

There are four scripts in the `solver` folder:
- `factorio_solver.py` is a the main user-facing script, and is a convenience wrapper to `linear_solve.py` with many configurable command line arguments.
- `linear_solver.py` contains the actually solving logic, and can be run directly with your own config file if you want more customization.
- `one_step_matrix_solver.py`, was the first script written and is kept for legacy purposes.
- `test_examples.py` runs everything in the `examples` folder and is useful for teting.

### Factorio Solver

To see a full list of command line args, we can run `python ./solver/factorio_solver.py --help`:

```
usage: Factorio Solver [-h] [-oi OUTPUT_ITEM] [-oa OUTPUT_AMOUNT] [-oq OUTPUT_QUALITY] [-pt PROD_MODULE_TIER] [-qt QUALITY_MODULE_TIER] [-s] [-st SPEED_MODULE_TIER] [-q MODULE_QUALITY]
                       [-pq PROD_MODULE_QUALITY] [-qq QUALITY_MODULE_QUALITY] [-sq SPEED_MODULE_QUALITY] [-bq BUILDING_QUALITY] [-mq MAX_QUALITY_UNLOCKED] [-ii [...]] [-iq INPUT_QUALITY] [-ir [...]]
                       [-av] [-ar ALLOWED_RECIPES [ALLOWED_RECIPES ...]] [-dr DISALLOWED_RECIPES [DISALLOWED_RECIPES ...]] [-ac ALLOWED_CRAFTING_MACHINES [ALLOWED_CRAFTING_MACHINES ...]]
                       [-dc DISALLOWED_CRAFTING_MACHINES [DISALLOWED_CRAFTING_MACHINES ...]] [-rc RESOURCE_COST] [-oc OFFSHORE_COST] [-mc MODULE_COST] [-bc BUILDING_COST] [-o OUTPUT] [-v]

This program optimizes prod/qual ratios in factories in order to optimize a given output

options:
  -h, --help            show this help message and exit
  -oi OUTPUT_ITEM, --output-item OUTPUT_ITEM
                        Output item to optimize. See data/space-age-2.0.11.json for item keys. (default: electronic-circuit)
  -oa OUTPUT_AMOUNT, --output-amount OUTPUT_AMOUNT
                        Output item amount per sec (default: 1.0)
  -oq OUTPUT_QUALITY, --output-quality OUTPUT_QUALITY
                        Output item quality (default: legendary)
  -pt PROD_MODULE_TIER, --prod-module-tier PROD_MODULE_TIER
                        Prod module tier (default: 3)
  -qt QUALITY_MODULE_TIER, --quality-module-tier QUALITY_MODULE_TIER
                        Quality module tier (default: 3)
  -s, --check-speed-modules
                        Check beaconed speed modules. (default: False)
  -st SPEED_MODULE_TIER, --speed-module-tier SPEED_MODULE_TIER
                        Speed module tier (default: 3)
  -q MODULE_QUALITY, --module-quality MODULE_QUALITY
                        Module quality (default: legendary)
  -pq PROD_MODULE_QUALITY, --prod-module-quality PROD_MODULE_QUALITY
                        Production module quality, overrides --module-quality (default: None)
  -qq QUALITY_MODULE_QUALITY, --quality-module-quality QUALITY_MODULE_QUALITY
                        Quality module quality, overrides --module-quality (default: None)
  -sq SPEED_MODULE_QUALITY, --speed-module-quality SPEED_MODULE_QUALITY
                        Speed module quality, overrides --module-quality (default: None)
  -bq BUILDING_QUALITY, --building-quality BUILDING_QUALITY
                        Building quality. Affects both crafting speed and beacon efficiency. (default: legendary)
  -mq MAX_QUALITY_UNLOCKED, --max-quality-unlocked MAX_QUALITY_UNLOCKED
                        Max quality unlocked (default: legendary)
  -ii [ ...], --input-items [ ...]
                        Custom input items to the solver. Should be phrased as item-1=cost-1 item-2=cost-2 ..., with no spaces around equals sign. (default: None)
  -iq INPUT_QUALITY, --input-quality INPUT_QUALITY
                        Input quality to the solver. Only used if --input-items flag is set. (default: normal)
  -ir [ ...], --input-resources [ ...]
                        Custom input resources to the solver. Should be phrased as resource-1=cost-1 resource-2=cost-2 ..., with no spaces around equals sign. If not present, uses all resources on all
                        planets. See data/space-age-2.0.11.json for resource keys. (default: None)
  -av, --allow-byproducts
                        Allows any item besides specified inputs or outputs to exist as a byproduct in the solution. Equivalent to adding void recipes. If not present, byproducts are recycled. (default:
                        False)
  -ar ALLOWED_RECIPES [ALLOWED_RECIPES ...], --allowed-recipes ALLOWED_RECIPES [ALLOWED_RECIPES ...]
                        Allowed recipes. Only one of {--allowed-recipes} or {--disallowed-recipes} can be used. See data/space-age-2.0.11.json for recipe keys. (default: None)
  -dr DISALLOWED_RECIPES [DISALLOWED_RECIPES ...], --disallowed-recipes DISALLOWED_RECIPES [DISALLOWED_RECIPES ...]
                        Disallowed recipes. Only one of {--allowed-recipes} or {--disallowed-recipes} can be used. See data/space-age-2.0.11.json for recipe keys. (default: None)
  -ac ALLOWED_CRAFTING_MACHINES [ALLOWED_CRAFTING_MACHINES ...], --allowed-crafting-machines ALLOWED_CRAFTING_MACHINES [ALLOWED_CRAFTING_MACHINES ...]
                        Allowed crafting machines. Only one of {--allowed-crafting-machines} or {--disallowed-crafting-machines} can be used. See data/space-age-2.0.11.json for crafting machine keys.
                        (default: None) (default: None)
  -dc DISALLOWED_CRAFTING_MACHINES [DISALLOWED_CRAFTING_MACHINES ...], --disallowed-crafting-machines DISALLOWED_CRAFTING_MACHINES [DISALLOWED_CRAFTING_MACHINES ...]
                        Disallowed crafting machines. Only one of {--disallowed-crafting-machines} or {--disdisallowed-crafting-machines} can be used. See data/space-age-2.0.11.json for crafting machine
                        keys. (default: None) (default: None)
  -rc RESOURCE_COST, --resource-cost RESOURCE_COST
                        Resource cost (default: 1.0)
  -oc OFFSHORE_COST, --offshore-cost OFFSHORE_COST
                        Offshore cost (default: 0.1)
  -mc MODULE_COST, --module-cost MODULE_COST
                        Module cost (default: 1.0)
  -bc BUILDING_COST, --building-cost BUILDING_COST
                        Module cost (default: 1.0)
  -o OUTPUT, --output OUTPUT
                        Output results to csv (if present) (default: None)
  -v, --verbose         Verbose mode. Prints out item and recipe information during setup. (default: False)
```

### Linear Solver

The linear solver can be run using any of the example config files, or you can write your own by copying one.
We can run the electronic_circuits example using `python ./solver/linear_solver.py --config ./examples/electronic_circuits.json`:

```
Solving...

Solution:
Objective value = 33.6992917762952

Inputs used:
input__normal__iron-ore-resource: 7.465629953826316
input__normal__copper-ore-resource: 3.4032654401274796

Modules used: 22.830396382341394

Recipes used:
normal__copper-cable__electromagnetic-plant__2-qual__3-prod: 0.6191747445909354
uncommon__copper-cable__electromagnetic-plant__0-qual__5-prod: 0.16277332419352578
rare__copper-cable__electromagnetic-plant__0-qual__5-prod: 0.01627733241935257
epic__copper-cable__electromagnetic-plant__0-qual__5-prod: 0.0016277332419352727
legendary__copper-cable__electromagnetic-plant__0-qual__5-prod: 0.0001808592491038949
normal__copper-plate__electric-furnace__0-qual__2-prod: 3.1498530596626044
uncommon__copper-plate__electric-furnace__0-qual__2-prod: 0.9349031953679429
rare__copper-plate__electric-furnace__0-qual__2-prod: 0.09349031953679429
epic__copper-plate__electric-furnace__0-qual__2-prod: 0.009349031953679431
legendary__copper-plate__electric-furnace__0-qual__2-prod: 0.001038781328186603
normal__electronic-circuit__electromagnetic-plant__2-qual__3-prod: 1.2925459199311295
uncommon__electronic-circuit__electromagnetic-plant__2-qual__3-prod: 1.0227096179006971
rare__electronic-circuit__electromagnetic-plant__1-qual__4-prod: 0.40866560782390005
epic__electronic-circuit__electromagnetic-plant__1-qual__4-prod: 0.18278872211418565
legendary__electronic-circuit__electromagnetic-plant__0-qual__5-prod: 0.039027219152938115
normal__electronic-circuit-recycling__recycler__4-qual__0-prod: 1.645330171952332
uncommon__electronic-circuit-recycling__recycler__4-qual__0-prod: 1.5114559803893002
rare__electronic-circuit-recycling__recycler__4-qual__0-prod: 0.8456581805768112
epic__electronic-circuit-recycling__recycler__4-qual__0-prod: 0.352564538480146
normal__iron-ore-recycling__recycler__4-qual__0-prod: 0.28880488665525983
normal__iron-plate__electric-furnace__0-qual__2-prod: 4.138906920396688
uncommon__iron-plate__electric-furnace__0-qual__2-prod: 2.2412745936954135
rare__iron-plate__electric-furnace__0-qual__2-prod: 0.22412745936954134
epic__iron-plate__electric-furnace__0-qual__2-prod: 0.02241274593695414
legendary__iron-plate__electric-furnace__0-qual__2-prod: 0.0024903051041060154
normal__copper-ore-mining__big-mining-drill__4-qual__0-prod: 1.1344218133758266
normal__iron-ore-mining__big-mining-drill__4-qual__0-prod: 2.488543317942105
```

### One Step Matrix Solver

This script optimizes the prod/qual modules at each quality stage in a recycling loop, and prints the number of low-quality inputs to high-quality outputs.
It also prints out any extra by-products, such as how many higher-quality items will be produced than the one being requested.
Note the recycler always has four quality modules.
All of the allowed parameters are shown below, and are also shown with the command `$ python ./main.py --help`:

```
This program optimizes prod/qual ratios in factories, and calculates outputs for a given input

options:
  -h, --help            show this help message and exit
  -st STARTING_TYPE, --starting-type STARTING_TYPE
                        Starting item type. String that is either 'ingredient' or 'product'. Ignored if --no-recycling flag is set, as starting type must be ingredient. (default: ingredient)
  -et ENDING_TYPE, --ending-type ENDING_TYPE
                        Ending item type. String that is either 'ingredient' or 'product'. Ignored if --no-recycling flag is set, as ending type must be product. (default: product)
  -pt PRODUCTIVITY_TIER, --productivity-tier PRODUCTIVITY_TIER
                        Productivity module tier. Number from 1 to 3. (default: 3)
  -qt QUALITY_TIER, --quality-tier QUALITY_TIER
                        Quality module tier. Number from 1 to 3. (default: 3)
  -q MODULE_QUALITY, --module-quality MODULE_QUALITY
                        Quality of the modules in the assembler and recycler (if present). Number from 1 to 5. (default: 5)
  -sq STARTING_QUALITY, --starting-quality STARTING_QUALITY
                        Starting quality ingredient. Number from 1 to 4. (default: 1)
  -eq ENDING_QUALITY, --ending-quality ENDING_QUALITY
                        Ending quality to optimize. Number from 2 to 5. Must be greater than starting quality. (default: 5)
  -mq MAX_QUALITY, --max-quality MAX_QUALITY
                        Max quality unlocked. Number from 3 to 5. Must be greater than or equal to ending quality. (default: 5)
  --enable-recycling, --no-enable-recycling
                        Enables recycling loops. Set this flag if you have unlocked the recycler. (default: True)
  -ms MODULE_SLOTS, --module-slots MODULE_SLOTS
                        number of module slots in the crafting building. (default: 4)
  -p ADDITIONAL_PROD, --additional-prod ADDITIONAL_PROD
                        any extra prod bonus, either from the building or recipe research. Units are percent out of 100. For example if using the foundry, enter 50. (default: 0)
```

The script is written in python and depends on the libraries in `requirements.txt`.
Detailed instructions on how to setup the required python environment is beyond the scope of this README, but if you're new to Python and want to run it, I would recommend the following steps:
1. search "how to install python {windows/mac/linux}" in google and get python available in the terminal or powershell.
2. use `git clone` to get a copy of this repository
3. use `virtualenv` to setup a virtual environment
4. run `pip install -r requirements.txt`
5. run `python ./main.py {--args}` to run the script

Some exmaples of the One Step Matrix Solver are shown below.

#### Example 1

Suppose you're really late-game and have access to legendary tier 3 modules, while using an assembler with four modules slots, and want a recycling loop that turns normal ingredients into legendary products (note this is script with all defaults).

Command:
```
python ./main.py
```

Output:

```
optimizing recycling loop that turns ingredient quality 1 into product quality 5

q1 input per q5 output: 79.87855759632312
recipe q1 uses 2 quality modules and 2 prod modules
recipe q2 uses 2 quality modules and 2 prod modules
recipe q3 uses 2 quality modules and 2 prod modules
recipe q4 uses 2 quality modules and 2 prod modules
recipe q5 uses 0 quality modules and 4 prod modules
```

#### Example 2

Suppose instead you're mid-game and have all tier 3 modules, but they are only level 2 quality (uncommon). Also suppose you haven't unlocked epic yet, and want to do a recycling loop that turns normal ingredients into uncommon products, and you're using the electromagnetics plant with 5 modules slots and built-in productivity of 50%.

Command:
```
$ python ./main.py --productivity-tier 3 --quality-tier 3 --module-quality 2 --starting-quality 1 --ending-quality 2 --max-quality 3 --module-slots 5 --additional-prod 50
```

Output:
```
optimizing recycling loop that turns ingredient quality 1 into product quality 2

q1 input per q2 output: 2.466913725362153
recipe q1 uses 5 quality modules and 0 prod modules
recipe q2 uses 0 quality modules and 5 prod modules

as an additional bonus you get the following for each q2 output:
q3 ingredient: 0.013713390145949652
q3 output: 0.08162732229731934

```

Now let's try the same as above but optimizing for rare outputs. We change `--ending-quality 2` to `--ending-quality 3`:
```
$ python ./main.py --productivity-tier 3 --quality-tier 3 --module-quality 2 --starting-quality 1 --ending-quality 3 --max-quality 3 --module-slots 5 --additional-prod 50

optimizing recycling loop that turns ingredient quality 1 into product quality 3

q1 input per q3 output: 8.524892733141074
recipe q1 uses 5 quality modules and 0 prod modules
recipe q2 uses 5 quality modules and 0 prod modules
recipe q3 uses 0 quality modules and 5 prod modules
```

So in this mid-game case the modules are more biased towards quality than prod.

#### Example 3

Suppose we're late-game (all modules are tier 3 legendary), and we want to turn an item into itself. Is it better to go up the production chain and down (craft then recycle), or down the production chain and back up (recycle then craft)? We'll just use normal assemblers (four module slots, no additional prod). This is where the `--starting-type` and `--ending-type` come in handy.

Going up-then-down the production chain gives 185.3 inputs/output:

```
python ./main.py --starting-type ingredient --ending-type ingredient

optimizing recycling loop that turns ingredient quality 1 into ingredient quality 5

q1 input per q5 output: 185.2831782227558
recipe q1 uses 2 quality modules and 2 prod modules
recipe q2 uses 2 quality modules and 2 prod modules
recipe q3 uses 1 quality modules and 3 prod modules
recipe q4 uses 0 quality modules and 4 prod modules
recipe q5 uses 0 quality modules and 4 prod modules
```

Going down-then-up the production chain gives around 171.5 inputs/output:

```
python ./main.py --starting-type product --ending-type product

optimizing recycling loop that turns product quality 1 into product quality 5

q1 input per q5 output: 171.5214553581744
recipe q1 uses 2 quality modules and 2 prod modules
recipe q2 uses 2 quality modules and 2 prod modules
recipe q3 uses 2 quality modules and 2 prod modules
recipe q4 uses 2 quality modules and 2 prod modules
recipe q5 uses 0 quality modules and 4 prod modules
```

So it's slightly better to go down-then-up, but not by much (171.5 vs 185.3).
