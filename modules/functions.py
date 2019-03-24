import csv
import math
import os

from .classes import Team
from .classes import Matchup
from .classes import Simulation


def str_to_bool(my_string):
	return my_string.lower() in ('true')


def run_simulation(strategy, n, decay):
	this_simulation = Simulation(strategy, n, decay, [])
	seed_odds = {}
	
	with open('data/seed_odds.csv', 'r', newline='') as infile:
		read = csv.reader(infile)
		next(read)

		for row in read:
			seed_odds[int(row[0])] = [float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), float(row[6])]

	team_odds = {}

	with open('data/team_odds.csv', 'r', newline='') as infile:
		read = csv.reader(infile)
		next(read)

		for row in read:
			team_odds[row[0]] = [float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), float(row[6])]

	teams = []

	with open('data/teams.csv', 'r', newline='') as infile:
		read = csv.reader(infile)
		next(read)

		for row in read:
			teams.append(Team(row[0], row[1], row[2]))

	with open('data/matchups.csv', 'r', newline='') as infile:
		read = csv.reader(infile)
		next(read)

		for row in read:
			target = row[2].split('-')[0]
			team_1 = int(row[2].split('-')[1])
			team_2 = int(row[3].split('-')[1])

			if target == 'team':
				this_simulation.matchups.append(Matchup(row[0], row[1], teams[team_1], teams[team_2], strategy, n, decay, team_odds, seed_odds))

			elif target == 'winner':
				this_simulation.matchups.append(Matchup(row[0], row[1], this_simulation.matchups[team_1].winner, this_simulation.matchups[team_2].winner, strategy, n, decay, team_odds, seed_odds))

	return this_simulation


def write_results(simulation):

	stats = {}

	if not os.path.exists('exports'):
		os.mkdir('exports')

	this_round = -1

	with open('exports/results-' + simulation.strategy + '_odds-' + str(simulation.n) + '_sims.txt', 'w') as text_file:

		for matchup in simulation.matchups:

			if matchup.tourney_round != this_round:
				this_round = matchup.tourney_round

				if this_round > 0:
					text_file.write('\n\n')

				text_file.write('Round of ' + str(int(64 / math.pow(2, this_round))) + '\n-----\n')

			if matchup.winner.name == matchup.team_1.name:

				if matchup.upset:
					text_file.write('(' + str(matchup.team_1.seed) + ') ' + matchup.team_1.name + ' upsets (' + str(matchup.team_2.seed) + ') ' + matchup.team_2.name + '\n')

				else:
					text_file.write('(' + str(matchup.team_1.seed) + ') ' + matchup.team_1.name + ' defeats (' + str(matchup.team_2.seed) + ') ' + matchup.team_2.name + '\n')

			else:

				if matchup.upset:
					text_file.write('(' + str(matchup.team_2.seed) + ') ' + matchup.team_2.name + ' upsets (' + str(matchup.team_1.seed) + ') ' + matchup.team_1.name + '\n')

				else:
					text_file.write('(' + str(matchup.team_2.seed) + ') ' + matchup.team_2.name + ' defeats (' + str(matchup.team_1.seed) + ') ' + matchup.team_1.name + '\n')

			if str(matchup.tourney_round) in stats:
				stats[str(matchup.tourney_round)] = [stats[str(matchup.tourney_round)][0] + 1, stats[str(matchup.tourney_round)][1] + 1] if matchup.upset else [stats[str(matchup.tourney_round)][0] + 1, stats[str(matchup.tourney_round)][1]]

			else:
				stats[str(matchup.tourney_round)] = [1, 1] if matchup.upset else [1, 0]

		text_file.write('\n--------------------\n\nSummary\n-----\n')

		for key in stats:
			text_file.write('Round ' + key + ': ' + str(stats[key][1]) + ' upsets in ' + str(stats[key][0]) + ' games.\n')

		text_file.write('\nTournament Champion: ' + simulation.matchups[len(simulation.matchups) - 1].winner.name + '\n')

	print('')

	for key in stats:
		print('Round ' + key + ': ' + str(stats[key][1]) + ' upsets in ' + str(stats[key][0]) + ' games.')

	print('\nTournament Champion: ' + simulation.matchups[len(simulation.matchups) - 1].winner.name + '\n')