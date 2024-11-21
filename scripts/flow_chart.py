import math
from collections import defaultdict

import linear_solver

class FlowChartGenerator:
    def __init__(self, solver_recipes, recipes, items, verbose):
        self.solver_recipes = solver_recipes
        self.recipes = recipes
        self.items = items
        self.verbose = verbose

    def get_localized_name(self, item_id, dictionary):
        """Get English localized name from dictionary, fallback to item_id if not found."""
        try:
            return dictionary[item_id]['localized_name']['en']
        except KeyError:
            return item_id

    def collect_recipe_variants(self):
        """Collect all recipe variants with non-zero solution values."""
        variants = defaultdict(list)
        
        for recipe_var in self.solver_recipes.values():
            if recipe_var.solution_value() > 1e-9:
                data = linear_solver.parse_recipe_id(recipe_var.name())
                data['solution_value'] = recipe_var.solution_value()
                
                recipe_name = data['recipe_name']
                if data['machine'] == 'recycler':
                    recipe_name = recipe_name.replace('-recycling', '')
                    
                variants[recipe_name].append(data)
                
        return variants

    def format_modules(self, num_qual, num_prod):
        """Format module string (e.g., '2Q1P' for 2 quality and 1 production modules)."""
        mods = []
        if int(num_qual):
            mods.append(f'{num_qual}Q')
        if int(num_prod):
            mods.append(f'{num_prod}P')
        return ' ' + ''.join(mods) if mods else ''

    def get_node_ids(self, recipe, variant):
        """Generate graph and class IDs for a variant."""
        graph_id = f'{recipe}_{variant["machine"]}_{variant["recipe_quality"]}'
        class_id = variant["recipe_quality"]
        
        if variant['machine'] == 'recycler':
            class_id += '-recycling'
            
        return graph_id, class_id

    def render_variant(self, recipe, variant_list, classes):
        """Render a single recipe variant as a Mermaid subgraph."""
        recipe_name = self.get_localized_name(recipe, self.recipes)
        output_lines = []
        
        for variant in variant_list:
            # Get localized names
            machine = self.get_localized_name(variant['machine'], self.items)
            name = self.get_localized_name(variant['recipe_name'], self.recipes)
            
            # Format modules string
            mods = self.format_modules(variant['num_qual_modules'], 
                                     variant['num_prod_modules'])
            
            # Generate IDs and track classes
            graph_id, class_id = self.get_node_ids(recipe, variant)
            classes[class_id].append(graph_id)
            
            # Create node definition
            node_text = (f'{graph_id}[{name.replace("(","").replace(")", "")} - '
                        f'{variant["recipe_quality"]} - {machine}{mods} x '
                        f'{math.ceil(variant["solution_value"])}]')
            output_lines.append(node_text)
            
        output_lines_str = '\n'.join(output_lines)
        return f"subgraph {recipe_name}\n{output_lines_str}\nend\n"

    def generate_class_definitions(self):
        """Generate Mermaid class definitions for different quality levels."""
        return """
    classDef normal fill:#BCBCBC
    classDef uncommon fill:#77E66A
    classDef rare fill:#4890F2
    classDef epic fill:#AF24F0
    classDef legendary fill:#EC9736
    classDef normal-recycling fill:#BCBCBC,stroke:#f5495a,stroke-width:4px
    classDef uncommon-recycling fill:#77E66A,stroke:#f5495a,stroke-width:4px
    classDef rare-recycling fill:#4890F2,stroke:#f5495a,stroke-width:4px
    classDef epic-recycling fill:#AF24F0,stroke:#f5495a,stroke-width:4px
    classDef legendary-recycling fill:#EC9736,stroke:#f5495a,stroke-width:4px"""

    def write_flow_chart(self, output_flow_chart):
        """Generate and save a Mermaid flow chart of the recipe system."""
        variants = self.collect_recipe_variants()
        classes = defaultdict(list)
        
        # Generate subgraphs for each recipe
        subgraphs = [
            self.render_variant(recipe, variant_list, classes)
            for recipe, variant_list in variants.items()
        ]
        
        # Generate class assignments
        class_assignments = [
            f"class {','.join(graph_ids)} {class_id}"
            for class_id, graph_ids in classes.items()
        ]
        
        subgraphs_str = '\n'.join(subgraphs)
        class_assignments_str = '\n'.join(class_assignments)
        # Combine all components into final sequence
        sequence = (
            "graph LR\n"
            f"{subgraphs_str}"
            f"{self.generate_class_definitions()}\n"
            f"{class_assignments_str}"
        )
        
        if self.verbose:
            print(sequence)

        html = f"""
        <!doctype html>
<html lang="en">
  <body>
    <pre class="mermaid">
        {sequence}
    </pre>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
    </script>
  </body>
</html>"""
        with open(output_flow_chart, 'w') as f:
            f.write(html)