# Web search guide — getting accurate, current information
web_search(query, max_results) returns snippets. Use it for facts that change. Use the browser guide when you must read a full page or interact.

## When to search
- Anything current: news, prices, scores, weather (use get_weather), versions, opening hours, "latest", "now", "today".
- Anything you are not sure about, or that the user will act on. Do not answer from memory for dates, prices or availability.

## How to query
- 2–6 specific words, include the year for time-sensitive things (the current year, not an old one). One topic per query.
- Names + context: "Anker 737 charger review" beats "good charger".
- No result? Reword with different keywords, or add the site name ("site:reddit.com", "site:docs.python.org").
- Multi-part question: one search per part, then combine.

## Going deeper than snippets
- web_open the best result URL, then web_read(full=True). Prefer official sites, docs, and primary sources over aggregators.
- Cross-check anything important with a second source. Say when sources disagree.

## Answering
- Lead with the answer, then one line of source and date. Short lists, no walls of text.
- If you could not verify something, say so plainly instead of guessing.
- Never paste long passages from articles; summarise in your own words.

## Useful direct URLs (use with web_open)
- Google: https://www.google.com/search?q=QUERY  · Maps: https://www.google.com/maps/search/QUERY
- Flights: https://www.google.com/travel/flights  · YouTube: https://www.youtube.com/results?search_query=QUERY
- Python docs: https://docs.python.org/3/search.html?q=QUERY  · GitHub: https://github.com/search?q=QUERY
- Package info: https://pypi.org/project/NAME  · https://www.npmjs.com/package/NAME
