Problem Statement
Investment teams need to allocate capital across multiple assets while balancing return, risk, liquidity, diversification, sector exposure, and investment constraints. In practice, portfolio optimization becomes difficult when real-world rules are added, such as maximum exposure per asset, minimum expected return, sector limits, number of assets to select, and risk tolerance. The challenge is to build a solution that recommends an optimized portfolio while satisfying these constraints.

Proposed Solution
Build a portfolio optimization simulator where users can select risk appetite, investment budget, number of assets, and constraints. The solution should start with a classical portfolio optimization baseline, then formulate a simplified asset selection problem as a binary optimization problem that can be tested using Qiskit or PennyLane simulators.
At a high level, the solution should: load historical or sample asset data, calculate expected returns and covariance, define portfolio constraints, run a classical optimizer, convert asset selection into QUBO, and test QAOA or VQE-style optimization on a simulator. The solution should also use agent-first design.

Business Value
The solution can help improve risk-adjusted returns, reduce concentration risk, improve diversification, and support faster investment decision-making. For the hackathon, participants can demonstrate value by comparing portfolio return, volatility, Sharpe ratio, diversification, and constraint satisfaction across classical and simulated quantum approaches.

