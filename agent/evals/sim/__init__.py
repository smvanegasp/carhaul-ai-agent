"""Stage 7: AI-vs-AI simulations. A caller model plays a persona, Mia answers with the fake
CarHauler API and geocoder, and code scores each call against its ground truth.

    cd agent && uv run python -m evals.sim.run --help

``catalog``: personas, ground truths, paths and their fragments. ``caller``: the simulated
caller. ``run``: one conversation, its score, and the CLI. ``report``: the files every run
leaves in ``evals/simulations/`` (public: the transcripts are part of the project's record).
"""
