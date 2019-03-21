import csv
import math
import os
import random
import sys

team_odds = {}
seed_odds = {}
matchups = []


class Team:

	def __init__(self, name, seed):
		self.name = name
		self.seed = int(seed)


class Matchup:

	def __init__(self, matchup_id, matchup_round, team_1, team_2, strategy, simulations):
		self.id = int(matchup_id)
		self.rnd = int(matchup_round)
		self.team_1 = team_1
		self.team_2 = team_2

		if strategy == 'team':
			self.team_1_odds = team_odds[team_1.name][self.rnd]
			self.team_2_odds = team_odds[team_2.name][self.rnd]
		
		elif strategy == 'seed':
			self.team_1_odds = seed_odds[team_1.seed][self.rnd]
			self.team_2_odds = seed_odds[team_2.seed][self.rnd]
		
		elif strategy == 'hybrid':
			self.team_1_odds = team_odds[team_1.name][self.rnd] + seed_odds[team_1.seed][self.rnd]
			self.team_2_odds = team_odds[team_2.name][self.rnd] + seed_odds[team_2.seed][self.rnd]
		
		self.team_1_odds = self.team_1_odds / (self.team_1_odds + self.team_2_odds)
		self.team_2_odds = self.team_2_odds / (self.team_1_odds + self.team_2_odds)
		self.team_1_score = 0
		self.team_2_score = 0

		for i in range(0, math.floor(simulations * (6 - self.rnd) / 6)):
			
			if random.random() <= self.team_1_odds:
				self.team_1_score += 1
			
			else:
				self.team_2_score += 1

		if self.team_1_score > self.team_2_score:
			self.winner = team_1
			self.upset = True if team_1.seed > team_2.seed else False

		elif self.team_1_score < self.team_2_score:
			self.winner = team_2
			self.upset = True if team_1.seed < team_2.seed else False

		else:

			if self.team_1.seed > self.team_2.seed:
				self.winner = team_1
				self.upset = True

			else:
				self.winner = team_2
				self.upset = True


def run_simulation(strategy, simulations):
	with open('data/seed_odds.csv', 'r', newline='') as infile:
		read = csv.reader(infile)
		next(read)

		for row in read:
			seed_odds[int(row[0])] = [float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), float(row[6])]

	with open('data/team_odds.csv', 'r', newline='') as infile:
		read = csv.reader(infile)
		next(read)

		for row in read:
			team_odds[row[0]] = [float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), float(row[6])]

	with open('data/matchups.csv', 'r', newline='') as infile:
		read = csv.reader(infile)
		next(read)

		for row in read:
			matchups.append(Matchup(row[0], row[1], Team(row[2], row[3]), Team(row[4], row[5]), strategy, simulations))

	with open('data/bracket.csv', 'r', newline='') as infile:
		read = csv.reader(infile)
		next(read)

		for row in read:
			matchups.append(Matchup(row[0], row[1], matchups[int(row[2])].winner, matchups[int(row[3])].winner, strategy, simulations))

	stats = {}

	if not os.path.exists('exports'):
		os.mkdir('exports')

	this_round = -1
	with open('exports/results-' + strategy + '_odds-' + str(simulations) + '_sims.txt', 'w') as text_file:

		for matchup in matchups:

			if matchup.rnd != this_round:
				this_round = matchup.rnd

				if this_round > 0:
					text_file.write('\n\n')

				text_file.write('Round of ' + str(int(64 / math.pow(2, this_round))) + '\n-----\n')

			if matchup.winner.name == matchup.team_1.name:

				if matchup.upset:
					text_file.write('(' + str(matchup.team_1.seed) + ') ' + matchup.team_1.name + ' upsets (' + str(matchup.team_2.seed) + ') ' + matchup.team_2.name + ' -- ' + str(matchup.team_1_score) + '-' + str(matchup.team_2_score) + '\n')

				else:
					text_file.write('(' + str(matchup.team_1.seed) + ') ' + matchup.team_1.name + ' defeats (' + str(matchup.team_2.seed) + ') ' + matchup.team_2.name + ' -- ' + str(matchup.team_1_score) + '-' + str(matchup.team_2_score) + '\n')

			else:

				if matchup.upset:
					text_file.write('(' + str(matchup.team_2.seed) + ') ' + matchup.team_2.name + ' upsets (' + str(matchup.team_1.seed) + ') ' + matchup.team_1.name + ' -- ' + str(matchup.team_2_score) + '-' + str(matchup.team_1_score) + '\n')

				else:
					text_file.write('(' + str(matchup.team_2.seed) + ') ' + matchup.team_2.name + ' defeats (' + str(matchup.team_1.seed) + ') ' + matchup.team_1.name + ' -- ' + str(matchup.team_2_score) + '-' + str(matchup.team_1_score) + '\n')

			if str(matchup.rnd) in stats:
				stats[str(matchup.rnd)] = [stats[str(matchup.rnd)][0] + 1, stats[str(matchup.rnd)][1] + 1] if matchup.upset else [stats[str(matchup.rnd)][0] + 1, stats[str(matchup.rnd)][1]]

			else:
				stats[str(matchup.rnd)] = [1, 1] if matchup.upset else [1, 0]

		text_file.write('\n--------------------\n\nSummary\n-----\n')

		for key in stats:
			text_file.write('Round ' + key + ': ' + str(stats[key][1]) + ' upsets in ' + str(stats[key][0]) + ' games.\n')

		text_file.write('\nTournament Champion: ' + matchups[len(matchups) - 1].winner.name + '\n')

	print('')

	for key in stats:
		print('Round ' + key + ': ' + str(stats[key][1]) + ' upsets in ' + str(stats[key][0]) + ' games.')

	print('\nTournament Champion: ' + matchups[len(matchups) - 1].winner.name + '\n')


if len(sys.argv) == 3:
	try:
		strategy = sys.argv[1]
		simulations = int(sys.argv[2])
	except:
		print('\nERROR: Input must be of format "' + sys.argv[0] + ' [seed|team|hybrid] [# of simulations]"\n')
	else:
		if strategy in ['seed', 'team', 'hybrid']:
			run_simulation(strategy, simulations)
		else:
			print('\nERROR: Input must be of format "' + sys.argv[0] + ' [seed|team|hybrid] [# of simulations]"\n')
else:
	print('\nERROR: Input must be of format "' + sys.argv[0] + ' [seed|team|hybrid] [# of simulations]"\n')
