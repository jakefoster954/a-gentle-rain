# How the heuristic plays

This describes `HeuristicAgent` (in [../src/agentle_rain/agents.py](../src/agentle_rain/agents.py)),
the online policy used by `estimate_win_probability` to estimate a tile set's win
rate. It plays a full game making only legal moves.

## Guiding principle

**Most‑constrained colour first.** Winning means blooming all colours, and each
2×2 hole can only ever bloom one of the (up to four) colours around it — so it's
essentially an assignment problem: cover every colour using the holes you build.
The agent therefore always prioritises the colours it currently has the **fewest
ways** to bloom, both when placing tiles and when choosing a bloom colour.

Everything below is derived live from the **current board** and the **set of
tiles still in the deck** — never the hidden draw order, and never anything
hardcoded about a specific tile set (colours, counts and layout are all read
dynamically). So it works unchanged if you edit the deck.

## Key terms

- **Available colour** — a colour not yet bloomed (still needed to win).
- **L‑shape** — a 2×2 block with three of its four cells filled: one tile short
  of a hole.
- **Completable** — an L‑shape whose empty cell *some remaining tile* can legally
  fill (matching all its neighbours in some rotation).
- **Source of a colour** — a completable L‑shape whose already‑fixed colours
  include that colour, i.e. a place you could still bloom it. A colour's number of
  sources measures how easy it is to get.
- **Criticality** = `1 / (1 + sources)` — a colour with fewer sources is more
  urgent (higher criticality).
- **Dead cell** — an empty cell next to a placement that **no** remaining tile can
  ever fill: a permanent gap.

## Choosing where to place a tile

For every legal placement the agent scores the resulting board and picks the best,
comparing these values **in order** (each only breaks ties in the ones above it):

1. **Immediate blooms** — the total *criticality* of the still‑needed colours this
   placement could bloom right now by completing a 2×2. (Finishing a hole for an
   urgent colour scores highest.)
2. **No dead cells** — placements that create a permanent unfillable gap are
   penalised.
3. **Setups** — for each completable, still‑needed L‑shape this placement creates,
   the criticality of its most urgent needed colour. This makes the agent
   **cultivate holes for under‑served colours** rather than easy ones.
4. **Variety** — the number of *distinct* still‑needed colours those setups cover
   (more independent routes to finishing all colours).
5. **Frontier** — prefer exposing edge colours that are still plentiful in the
   deck, so future tiles can attach and more 2×2s become possible.
6. **Compactness** — a final tie‑break favouring placements touching more existing
   tiles (denser tableaux create more holes).

If (rarely) nothing scores, it falls back to any legal placement.

## Choosing which colour blooms

When a 2×2 completes and several still‑needed colours surround it, the agent
blooms the **most constrained** one — the colour it is least able to get
elsewhere. Candidates are compared by, in order:

1. **Fewest other sources** — other open holes plus completable L‑shapes that
   could also yield this colour. Spend the colour with the fewest alternatives;
   keep the flexible ones for later holes.
2. **Scarcer in the deck** — as a tie‑break, prefer the colour with fewer copies
   left among the remaining tiles.
3. Lowest colour id, purely to make the choice deterministic.

## Notes

- It only ever uses the remaining **set** of tiles (perfect memory), so it's a
  legitimate online player; given the same position it always decides the same
  way.
- It is a strong heuristic, **not optimal** — on the bundled placeholder deck it
  wins ~99% of shuffles. Most remaining losses are shuffles where the holes that
  could be built simply cannot cover every colour.
- See [diagnose_losses.py](../tools/diagnose_losses.py) for the tool that analyses
  why games are lost.
