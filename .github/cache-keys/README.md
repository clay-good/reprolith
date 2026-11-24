# Per-job pip cache keys

`actions/setup-python`'s pip cache keys on the interpreter version and the hash of the files named
in `cache-dependency-path` — and on nothing else. Every job here installs from the same
`pyproject.toml`, so every job computed the **same key** while installing a different set of
extras. The lightest one wins the race, saves a cache with none of the heavy wheels in it, and
every later job gets a hit it cannot use: `python (3.9)` installs `[dev]` in four minutes while
`engine (3.9)` spends twenty-three compiling `python-copasi`, which publishes an sdist and no 3.9
wheel. Measured on run 45338935301.

Each file here names one job's extras. It is listed beside `pyproject.toml` in that job's
`cache-dependency-path`, so the hash differs per job and each keeps its own cache. The content is
what makes the key, so it has to change when the job's extras change — which is also why it is
worth reading: it is the only place the extras each job installs are written down in one line.
