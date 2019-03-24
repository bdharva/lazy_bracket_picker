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

with open('exports/results-insanity.csv', 'w') as output:
	writer = csv.writer(output, lineterminator='\n')
	writer.writerow(['sim_id', 'matchup_id','round_id','team_1_id','team_2_id','winner_id'])

	for i in ['seed', 'team', 'hybrid']:

		print(i)

		for j in range(1, 51):

			print(j)

			for k in [True, False]:

				for l in range(0,10000):

					for matchup in run_simulation(i, j, k).matchups:

						writer.writerow([i + '-' + str(j).zfill(3) + '-' + str(k) + '-' + str(l).zfill(5), matchup.matchup_id, matchup.tourney_round, matchup.team_1.team_id, matchup.team_2.team_id, matchup.winner.team_id])