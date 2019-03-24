import math
import random


class Team:

	def __init__(self, team_id, name, seed):
		self.team_id = int(team_id)
		self.name = name
		self.seed = int(seed)


class Matchup:

	def __init__(self, matchup_id, tourney_round, team_1, team_2, strategy, n, decay, team_odds, seed_odds):
		self.matchup_id = int(matchup_id)
		self.tourney_round = int(tourney_round)
		self.team_1 = team_1
		self.team_2 = team_2

		if strategy == 'team':
			self.team_1_odds = team_odds[team_1.team_id][self.tourney_round]
			self.team_2_odds = team_odds[team_2.team_id][self.tourney_round]
		
		elif strategy == 'seed':
			self.team_1_odds = seed_odds[team_1.seed][self.tourney_round]
			self.team_2_odds = seed_odds[team_2.seed][self.tourney_round]

		elif strategy == 'hybrid':
			self.team_1_odds = team_odds[team_1.team_id][self.tourney_round] + seed_odds[team_1.seed][self.tourney_round]
			self.team_2_odds = team_odds[team_2.team_id][self.tourney_round] + seed_odds[team_2.seed][self.tourney_round]

		try:
			self.team_1_odds = self.team_1_odds / (self.team_1_odds + self.team_2_odds)

		except ZeroDivisionError:
			self.team_1_odds = 0

		try:
			self.team_2_odds = self.team_2_odds / (self.team_1_odds + self.team_2_odds)

		except ZeroDivisionError:
			self.team_2_odds = 0

		self.team_1_score = 0
		self.team_2_score = 0

		if decay:
			n = math.floor(n * (6 - self.tourney_round) / 6)

		for i in range(0, n):

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

			elif self.team_1.seed < self.team_2.seed:
				self.winner = team_2
				self.upset = True

			else:

				if self.team_1_odds > self.team_2_odds:
					self.winner = team_2
					self.upset = False

				else:
					self.winner = team_1
					self.upset = False


class Simulation:
	def __init__(self, strategy, n, decay, matchups):
		self.strategy = strategy
		self.n = n
		self.decay = decay
		self.matchups = matchups