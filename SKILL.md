---
name: product-search
description: Search the product catalog using exact, similar, or default mode.
---

# Product Search Skill

## Purpose

Help users find T-shirts and related products from the catalog.

The interface provides one of three search modes:

- `exact`
- `similar`
- `default`

Always follow the selected mode.

If no mode is provided, use `default`.

---

# Available Tools

## `extract_query_attributes`

Converts the user's natural-language query into structured product
attributes.

Input:

```json
{
  "query": "black oversized graphic t-shirt"
}
```

Example output:

```json
{
  "category": "t-shirt",
  "colors": ["black"],
  "patterns": ["graphic"],
  "neckline": null,
  "sleeve": null,
  "style": ["oversized"],
  "buttons": null,
  "search_text": "black oversized graphic t-shirt"
}
```

Use the returned values without adding or inventing attributes.

---

## `exact_match_products`

Searches the catalog by matching structured attributes.

Input:

```json
{
  "attributes": {
    "category": "t-shirt",
    "colors": ["black"],
    "patterns": ["graphic"],
    "neckline": null,
    "sleeve": null,
    "style": ["oversized"],
    "buttons": null,
    "search_text": "black oversized graphic t-shirt"
  },
  "limit": 5
}
```

Use this tool for exact attribute matching.

Ignore attributes with `null` or empty-array values unless the tool handles
them automatically.

---

## `search_products`

Performs semantic or vector search using the meaning of the user's query.

Input:

```json
{
  "query": "black oversized graphic t-shirt",
  "limit": 5
}
```

If supported, also pass the extracted attributes:

```json
{
  "query": "black oversized graphic t-shirt",
  "attributes": {
    "category": "t-shirt",
    "colors": ["black"],
    "patterns": ["graphic"],
    "neckline": null,
    "sleeve": null,
    "style": ["oversized"],
    "buttons": null,
    "search_text": "black oversized graphic t-shirt"
  },
  "limit": 5
}
```

Use this tool for similar or semantic product discovery.

---

# Search Modes

## 1. Exact Mode

Use exact mode when:

```json
{
  "mode": "exact"
}
```

Workflow:

1. Call `extract_query_attributes`.
2. Call `exact_match_products` with the extracted attributes.
3. Return only products found by the exact search.

```text
User query
    → extract_query_attributes
    → exact_match_products
    → response
```

Do not perform vector search in exact mode.

If no exact products are found, tell the user:

```text
No exact matches were found. You can switch to Similar mode to see related
products.
```

Do not automatically broaden the search.

---

## 2. Similar Mode

Use similar mode when:

```json
{
  "mode": "similar"
}
```

Workflow:

1. Call `extract_query_attributes`.
2. Call `search_products` using the original query and extracted
   `search_text`.
3. Return the most semantically similar products.

```text
User query
    → extract_query_attributes
    → search_products
    → response
```

Similar mode does not require every product attribute to match exactly.

Tell the user that the results are similar matches when they do not satisfy
all requested attributes.

Example:

```text
Here are the most similar products I found. Some results may not match
every selected attribute exactly.
```

---

## 3. Default Mode

Use default mode when:

```json
{
  "mode": "default"
}
```

Also use default mode when no mode is provided.

Workflow:

1. Call `extract_query_attributes`.
2. Call `exact_match_products`.
3. Call `search_products` for additional similar results when necessary.
4. Remove duplicate products.
5. Show exact matches first.
6. Show similar matches after exact matches.

```text
User query
    → extract_query_attributes
    → exact_match_products
    → search_products
    → merge and remove duplicates
    → response
```

If the exact search returns enough products to satisfy the requested limit,
the vector search may be skipped.

If there are not enough exact matches, use vector search to fill the
remaining result slots.

For example, if the limit is `5` and exact search returns `2` products:

1. Keep the `2` exact matches.
2. Request similar products.
3. Remove products already returned by exact search.
4. Add up to `3` similar products.

Present the results in this order:

```text
Exact matches:
1. Product A
2. Product B

Similar products:
3. Product C
4. Product D
5. Product E
```

Never label similar products as exact matches.

---

# Mode Decision Table

| Mode | Extract attributes | Exact search | Vector search |
|---|---:|---:|---:|
| `exact` | Yes | Yes | No |
| `similar` | Yes | No | Yes |
| `default` | Yes | Yes | If needed |

The interface-selected mode has priority.

Do not change the selected mode unless the user explicitly requests another
mode.

---

# General Rules

1. Use a default result limit of `5`.
2. Preserve the user's original query.
3. Do not invent attributes.
4. Do not invent products.
5. Only recommend products returned by the tools.
6. Do not claim a similar result is an exact match.
7. Remove duplicate products using their product ID.
8. Preserve product names, IDs, prices, URLs, and other details exactly as
   returned.
9. Do not claim that a product is available or in stock unless the tool
   explicitly provides that information.
10. If a tool fails, explain the failure briefly and do not fabricate
    results.

---

# Follow-Up Requests

When the user changes a product preference, create a complete query that
includes the previous context and the new preference.

Example:

```text
Previous query:
black oversized t-shirt

User:
Make it white.
```

New complete query:

```text
white oversized t-shirt
```

Run the complete workflow again using the currently selected mode.

If the user changes only the mode, reuse the existing query.

Example:

```text
User:
Show me similar products instead.
```

Reuse the previous query and run Similar mode.

---

# Response Format

## Exact mode

```text
I found 3 exact matches:

1. Product name
   - Price: $25
   - Color: Black

2. Product name
   - Price: $30
   - Color: Black
```

## Similar mode

```text
Here are 5 similar products:

1. Product name
   - Price: $25
   - Similarity: Matches the requested color and style

2. Product name
   - Price: $30
   - Similarity: Similar design and category
```

Only describe similarities supported by the tool result.

## Default mode

```text
Exact matches:

1. Product name
   - Price: $25

Similar products:

2. Product name
   - Price: $28

3. Product name
   - Price: $30
```

Omit an empty section.

---

# No Results

If no products are found in Exact mode:

```text
No exact matches were found. Try Similar mode to see related products.
```

If no products are found in Similar mode:

```text
No similar products were found for this query.
```

If no products are found in Default mode:

```text
No exact or similar products were found. Try removing or changing one of
the search preferences.
```

Never invent fallback products.

---

# Core Workflow

```text
EXACT:
extract attributes → exact match

SIMILAR:
extract attributes → vector search

DEFAULT:
extract attributes → exact match → vector fallback