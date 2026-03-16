import csv
import math
import os
import random
import sys

from modules.functions import run_simulation
from modules.classes import Matchup
from modules.classes import Team

team_odds = {}
seed_odds = {}
teams = []


if not os.path.exists('exports'):
	os.mkdir('exports')

if not os.path.exists('exports/bulk'):
	os.mkdir('exports/bulk')

for i in ['seed', 'team', 'hybrid']:
	print(i)

	for j in range(1, 101):
		print(j)

		for k in [True, False]:
			group = i + '-' + str(j).zfill(3) + '-' + str(k)

			with open('exports/bulk/' + group + '.csv', 'w') as output:
				writer = csv.writer(output, lineterminator='\n')
				writer.writerow(['id', 'results'])

				for l in range(0,10000):
					sim_id = group + '-' + str(l).zfill(5)
					sim_results = ''

					for matchup in run_simulation(i, j, k).matchups:
						sim_results = sim_results + '-' + str(matchup.winner.team_id)

					writer.writerow([sim_id, sim_results])