# Lazy Bracket Picker
_Don't know/care about college basketball, but feel socially obligated to join friends/family/co-workers in a March Madness bracket pool? This is for you._

The program accepts commands of the format `simulate.py [seed|team|hybrid] [# of simulations]`. The first argument indicates the odds you'd like to use for the simulations. Seed-based uses the historic probability of a given seed reaching a given round of the tournament, team-based uses AccuScore's probability of a given team reaching a given round of the tournament, and hybrid simply blends the two. The second argument indicates how many simulations you'd like to run for each game in the tournament.

Larger numbers will follow the odds more closely, while fewer simulation will introduce more randomness into outcomes. I've found that 10-20 simulations per game generally yields a nice round-by-round distribution of upsets that is roughly in line with historical outcomes (since 1985, when the tournament field was expanded to 64 teams):

| Round | Average | Least | Most |
| --- | --- | --- | --- |
| First Round | 6.1 | 2 (2007) | 10 (2016) |
| Second Round | 3.7 | 0 (3 occasions) | 8 (2000) |
| Sweet 16 | 1.7 | 0 (5 occasions) | 4 (1990) |
| Elite Eight | 0.5 | 0 (10 occasions) | 2 (2 occasions) |
| Final Four | 0.2 | 0 (23 occasions) | 2 (2014) |
| **Total Upsets** | **12.7** | **4 (2007)** | **19 (2014)** |

I suggest just slamming around in Terminal until you see an upset distribution that you like and a champion you can live with:

![Screenshot of Terminal](assets/terminal.png?raw=true)

When you're ready to fill out your bracket, the full results of your simulation are saved in the project's `exports/` directory, following the format `results-[seed|team|hybrid]_odds-[# of simulations]_sims.txt`.

![Screenshot of Sublime](assets/sublime.png?raw=true)

Enjoy.