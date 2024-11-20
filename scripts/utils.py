def parse_recipe_id(recipe_id):
    objs = recipe_id.split('__')
    return {
        'recipe_quality': objs[0],
        'recipe_name': objs[1],
        'machine': objs[2],
        'num_qual_modules': objs[3].split('-')[0],
        'num_prod_modules': objs[4].split('-')[0]
    }