/**
 * Curated recipe bodies for the printable page (CloakVault v3).
 *
 * These are REAL, human-quality recipes carrying ZERO payload. The body and
 * the footer payload are fully independent: changing the recipe never changes
 * the payload and vice versa (proved in codec tests). They are fixed
 * templates, not procedurally generated — uniformity is a detectable
 * signature, so these read like recipes a person would actually print.
 */
export interface CuratedRecipe {
  id: string;
  title: string;
  body: string; // plain text, printed as-is
}

export const CURATED_RECIPES: CuratedRecipe[] = [
  {
    id: 'traybake',
    title: 'Harissa Roast Vegetable Traybake',
    body: `A hands-off supper of caramelised roots under a smoky-sweet glaze, finished with lemon, feta and herbs.

Serves 4. About 55 minutes, most of it in the oven.

For the tray
700g carrots, scrubbed and halved lengthways
500g parsnips, peeled and quartered
400g baby potatoes, left whole
2 red onions, cut into thick wedges
1 small cauliflower, broken into florets
3 tablespoons olive oil
2 tablespoons harissa paste
1 tablespoon honey
1 teaspoon cumin seeds
half a teaspoon of flaky salt

To finish
1 lemon, halved
100g feta, crumbled
a small handful of parsley, roughly chopped
2 tablespoons toasted flaked almonds

1. Heat the oven to 200C (fan 180C). Line your largest roasting tray with baking paper.
2. Tumble the carrots, parsnips and potatoes onto the tray. Whisk the oil with the harissa and honey, pour it over, and turn everything until glossy.
3. Roast for 25 minutes, then add the onions and cauliflower, scatter over the cumin seeds and salt, and toss once.
4. Roast for a further 20 minutes, until the edges are scorched in places and a knife slips easily through the thickest piece of carrot.
5. Squeeze the lemon over the hot tray, then scatter with the feta, parsley and almonds.
6. Rest for five minutes so the juices settle, then serve straight from the tray.

Notes
Swap the parsnips for beetroot if you like it earthier, or add a drained tin of chickpeas along with the onions to make it more of a meal. Leftovers keep for two days and are very good stuffed into warm flatbreads.`,
  },
  {
    id: 'granola',
    title: 'Maple Oven Granola',
    body: `A big jar of deeply toasted clusters, sweet with maple and heavy with nuts and seeds.

Makes about 1 kg (two large jars). Hands-on 15 min. Bake 35 min. Oven 150C (fan 130C).

Dry
300g jumbo rolled oats
100g rye flakes
50g coconut flakes
100g whole almonds
75g pecans, roughly chopped
75g cashews, halved
50g pumpkin seeds
50g sunflower seeds
25g sesame seeds
1 tsp ground cinnamon
half a tsp ground ginger
half a tsp fine salt

Wet
80ml maple syrup
60ml sunflower oil
50g light brown sugar
1 tsp vanilla extract

To finish
100g raisins
75g dried apricots, chopped
finely grated zest of 1 orange

1. Heat the oven to 150C (fan 130C) and line two large baking trays.
2. Mix all the dry ingredients in your biggest bowl.
3. Warm the maple syrup, oil, sugar and vanilla in a small pan for 2 min, stirring until the sugar dissolves.
4. Pour the wet mix over the dry and stir until every flake looks glossy. Spread over the trays and press down firmly with the back of a spoon.
5. Bake for 35 min, stirring once at 20 min and swapping the trays around, until deep golden at the edges.
6. Cool completely on the trays without stirring so that clusters form, then mix in the raisins, apricots and zest.

Notes
Any nut works at the same weights; hazelnuts or walnuts in place of the almonds are especially good. Swap the raisins for dried cherries for a sharper jar. Keeps 3 weeks in an airtight jar.`,
  },
  {
    id: 'soup',
    title: 'Smoky Tomato and White Bean Soup',
    body: `A fifteen-minute store-cupboard soup that tastes like it simmered all afternoon.

Serves 2 generously. Ready in 20 minutes.

2 tablespoons olive oil
1 onion, finely chopped
2 cloves of garlic, sliced
1 teaspoon smoked paprika
a pinch of chilli flakes
400g tin of chopped tomatoes
400g tin of cannellini beans, drained
400ml vegetable stock
1 teaspoon red wine vinegar
a handful of basil leaves
grated parmesan and good bread, to serve

1. Warm the oil in a deep pan over a medium heat and soften the onion for 5 minutes without letting it colour.
2. Add the garlic, paprika and chilli flakes and cook for 1 minute more, until the kitchen smells of it.
3. Tip in the tomatoes, beans and stock, bring to a simmer, and let it bubble gently for 10 minutes.
4. Crush a few beans against the side of the pan to thicken the soup, then stir in the vinegar and most of the basil.
5. Taste for salt, ladle into bowls, and finish with the last basil leaves, a grating of parmesan and plenty of bread.

Notes
A rind of parmesan dropped in with the stock makes it deeper; fish it out before serving. Swap the cannellini for butter beans if that is what the cupboard has.`,
  },
  {
    id: 'pancakes',
    title: 'Saturday Oat Pancakes',
    body: `Soft, faintly sweet pancakes that come together in one jug while the pan heats.

Makes about 10 small pancakes. 25 minutes start to finish.

150g plain flour
50g porridge oats
2 teaspoons baking powder
2 tablespoons caster sugar
a pinch of fine salt
1 egg
250ml milk
25g butter, melted, plus more for the pan
1 teaspoon vanilla extract
berries, yoghurt and honey, to serve

1. Whisk the flour, oats, baking powder, sugar and salt together in a jug.
2. Beat in the egg, then the milk, melted butter and vanilla, until you have a thick, pourable batter. Let it stand for 5 minutes so the oats soften.
3. Heat a knob of butter in a wide frying pan over a medium heat until it foams.
4. Drop in tablespoons of batter, spacing them well, and cook for 2 minutes until bubbles rise and pop on the surface.
5. Flip and cook for 1 minute more, until both sides are deep gold. Keep warm under a tea towel while you finish the rest.
6. Pile onto plates with berries, a spoonful of yoghurt and a thread of honey.

Notes
The batter keeps overnight in the fridge and is arguably better for it; loosen it with a splash of milk in the morning. For fluffier pancakes, separate the egg and fold the whisked white in last.`,
  },
];

export function recipeById(id: string): CuratedRecipe {
  const r = CURATED_RECIPES.find((x) => x.id === id);
  if (!r) throw new Error(`unknown recipe: ${id}`);
  return r;
}
