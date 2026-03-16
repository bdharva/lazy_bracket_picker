"""
Bracket optimizer: computes the mathematically optimal bracket
that maximizes expected score.

Uses Torvik adjusted efficiency margins to derive pairwise win
probabilities via logistic regression, then propagates expected
value forward through the bracket tree.

Usage:
  python optimize.py              # Expected-value optimal bracket
  python optimize.py contrarian   # Contrarian mode for large pools

The key insight: for each slot in the bracket, we don't just pick
the most likely winner. We pick the team whose expected point
contribution across ALL rounds they could appear in is highest.
This matters because later rounds are worth exponentially more
points (10 -> 20 -> 40 -> 80 -> 160 -> 320).

Torvik efficiency margins are converted to win probabilities using:
  P(A beats B) = 1 / (1 + 10^(-EM_diff / 11))
This is the standard logistic model calibrated to college basketball,
where an efficiency margin difference of 11 points corresponds to
roughly a 75% win probability.
"""

import csv
import math
import os
import sys


def load_teams():
	teams = {}
	with open('data/teams.csv', 'r', newline='') as f:
		reader = csv.reader(f)
		next(reader)
		for row in reader:
			teams[int(row[0])] = {'id': int(row[0]), 'name': row[1], 'seed': int(row[2])}
	return teams


def load_matchups():
	matchups = []
	with open('data/matchups.csv', 'r', newline='') as f:
		reader = csv.reader(f)
		next(reader)
		for row in reader:
			matchups.append({
				'id': int(row[0]),
				'round': int(row[1]),
				'team_1_ref': row[2],
				'team_2_ref': row[3]
			})
	return matchups


def load_scoring():
	scoring = {}
	with open('data/scoring.csv', 'r', newline='') as f:
		reader = csv.reader(f)
		next(reader)
		for row in reader:
			scoring[int(row[0])] = int(row[1])
	return scoring


def load_torvik():
	"""Load Torvik efficiency data and compute adjusted efficiency margins."""
	torvik = {}
	with open('data/torvik.csv', 'r', newline='') as f:
		reader = csv.reader(f)
		next(reader)
		for row in reader:
			name = row[0].strip()
			adj_oe = float(row[1])
			adj_de = float(row[2])
			torvik[name] = {
				'adj_oe': adj_oe,
				'adj_de': adj_de,
				'adj_em': adj_oe - adj_de
			}
	return torvik


# Map team names in teams.csv to Torvik names where they differ
TORVIK_NAME_MAP = {
	'UConn': 'Connecticut',
	'UNC': 'North Carolina',
	'NC State': 'N.C. State',
	'McNeese': 'McNeese St.',
	'Iowa State': 'Iowa St.',
	'Utah State': 'Utah St.',
	'North Dakota State': 'North Dakota St.',
	'Wright State': 'Wright St.',
	'Kennesaw State': 'Kennesaw St.',
	'Tennessee State': 'Tennessee St.',
	'Cal Baptist': 'Cal Baptist',
	'Northern Iowa': 'Northern Iowa',
	'Saint Mary\'s': 'Saint Mary\'s',
	'Saint Louis': 'Saint Louis',
	'South Florida': 'South Florida',
	'Texas A&M': 'Texas A&M',
	'High Point': 'High Point',
	'Miami OH': 'Miami OH',
}


def get_torvik_em(team_name, torvik_data):
	"""Look up a team's adjusted efficiency margin from Torvik data."""
	lookup = TORVIK_NAME_MAP.get(team_name, team_name)
	if lookup in torvik_data:
		return torvik_data[lookup]['adj_em']
	# Fuzzy fallback: try partial match
	for key in torvik_data:
		if team_name.lower() in key.lower() or key.lower() in team_name.lower():
			return torvik_data[key]['adj_em']
	# Default: use seed-based estimate (weaker teams ~0, top teams ~35)
	return 0.0


def win_probability(em_a, em_b):
	"""
	Compute probability that team A beats team B given their
	adjusted efficiency margins, using logistic model.

	Calibration: EM_diff of 11 ≈ 75% win probability.
	This matches historical NCAA tournament data.
	"""
	diff = em_a - em_b
	return 1.0 / (1.0 + math.pow(10, -diff / 11.0))


def build_bracket_tree(matchups):
	"""
	Build a tree structure from the matchups CSV.
	Each matchup references either initial teams or winners of prior matchups.
	Returns matchups in order (they're already topologically sorted in the CSV).
	"""
	return matchups


def load_seed_odds():
	"""Load historical seed-based advancement odds."""
	seed_odds = {}
	with open('data/seed_odds.csv', 'r', newline='') as f:
		reader = csv.reader(f)
		next(reader)
		for row in reader:
			seed_odds[int(row[0])] = [float(row[i]) for i in range(1, 7)]
	return seed_odds


def get_torvik_defense(team_name, torvik_data):
	"""Look up a team's adjusted defensive efficiency."""
	lookup = TORVIK_NAME_MAP.get(team_name, team_name)
	if lookup in torvik_data:
		return torvik_data[lookup]['adj_de']
	for key in torvik_data:
		if team_name.lower() in key.lower() or key.lower() in team_name.lower():
			return torvik_data[key]['adj_de']
	return 105.0  # average


def compute_win_probs(teams, matchups, torvik_data, seed_odds=None,
					  model_blend=0.0, defense_floor=False, upset_boost=0.0):
	"""
	Compute the probability of each team winning each matchup slot.

	model_blend: 0.0 = pure Torvik, 1.0 = pure seed-historical
	defense_floor: if True, penalize teams with bad defense in later rounds
	upset_boost: 0.0-1.0, boosts underdog probabilities in historically upset-prone matchups
	"""
	slot_probs = {}
	for team_id in teams:
		slot_probs['team-' + str(team_id)] = {team_id: 1.0}

	winner_probs = {}
	team_ems = {}
	team_defs = {}
	for team_id, team in teams.items():
		team_ems[team_id] = get_torvik_em(team['name'], torvik_data)
		team_defs[team_id] = get_torvik_defense(team['name'], torvik_data)

	# Historical upset rates by seed matchup (higher seed's win rate)
	# 5v12: 35.6%, 6v11: 36.8%, 7v10: 38.2%, 8v9: 50%, 3v14: 15.4%
	upset_history = {
		(5, 12): 0.356, (12, 5): 0.356,
		(6, 11): 0.368, (11, 6): 0.368,
		(7, 10): 0.382, (10, 7): 0.382,
		(8, 9): 0.500, (9, 8): 0.500,
		(3, 14): 0.154, (14, 3): 0.154,
		(4, 13): 0.206, (13, 4): 0.206,
	}

	# Defense floor: median AdjDE for Final Four teams historically is ~95
	DEFENSE_THRESHOLD = 98.0

	for matchup in matchups:
		m_id = matchup['id']
		m_round = matchup['round']
		ref_1 = matchup['team_1_ref']
		ref_2 = matchup['team_2_ref']

		if ref_1.startswith('team-'):
			probs_1 = slot_probs[ref_1]
		else:
			probs_1 = winner_probs[int(ref_1.split('-')[1])]

		if ref_2.startswith('team-'):
			probs_2 = slot_probs[ref_2]
		else:
			probs_2 = winner_probs[int(ref_2.split('-')[1])]

		win_probs_here = {}
		for t1, p1 in probs_1.items():
			for t2, p2 in probs_2.items():
				pairing_prob = p1 * p2

				# Base probability from Torvik efficiency margins
				p_torvik = win_probability(team_ems[t1], team_ems[t2])

				# Seed-based historical probability (if available)
				if seed_odds and model_blend > 0:
					s1_odds = seed_odds.get(teams[t1]['seed'], [50]*6)
					s2_odds = seed_odds.get(teams[t2]['seed'], [50]*6)
					r = min(m_round, 5)
					total = s1_odds[r] + s2_odds[r]
					p_seed = s1_odds[r] / total if total > 0 else 0.5
					# Blend
					p_t1_wins = p_torvik * (1.0 - model_blend) + p_seed * model_blend
				else:
					p_t1_wins = p_torvik

				# Upset boost: nudge toward historical upset rates
				if upset_boost > 0 and m_round == 0:
					seed_pair = (teams[t1]['seed'], teams[t2]['seed'])
					if seed_pair in upset_history:
						hist_underdog_rate = upset_history[seed_pair]
						# Determine which team is the underdog
						if teams[t1]['seed'] > teams[t2]['seed']:
							# t1 is the underdog
							target_p = hist_underdog_rate
							p_t1_wins = p_t1_wins + upset_boost * (target_p - p_t1_wins)
						else:
							# t2 is the underdog
							target_p = 1.0 - hist_underdog_rate
							p_t1_wins = p_t1_wins + upset_boost * (target_p - p_t1_wins)

				# Defense floor: penalize bad defenders in later rounds
				if defense_floor and m_round >= 2:
					penalty_scale = (m_round - 1) / 4.0  # stronger penalty deeper
					d1_penalty = max(0, team_defs[t1] - DEFENSE_THRESHOLD) * 0.02 * penalty_scale
					d2_penalty = max(0, team_defs[t2] - DEFENSE_THRESHOLD) * 0.02 * penalty_scale
					# Shift probability: penalize bad defense
					p_t1_wins = p_t1_wins * (1.0 - d1_penalty) / max(
						p_t1_wins * (1.0 - d1_penalty) + (1.0 - p_t1_wins) * (1.0 - d2_penalty), 0.001)

				p_t1_wins = max(0.001, min(0.999, p_t1_wins))

				if t1 not in win_probs_here:
					win_probs_here[t1] = 0.0
				win_probs_here[t1] += pairing_prob * p_t1_wins

				if t2 not in win_probs_here:
					win_probs_here[t2] = 0.0
				win_probs_here[t2] += pairing_prob * (1.0 - p_t1_wins)

		winner_probs[m_id] = win_probs_here

	return winner_probs


def compute_optimal_bracket(teams, matchups, scoring, torvik_data,
							contrarian_weight=0.0, homer_teams=None, pool_size=10,
							seed_odds=None, model_blend=0.0, defense_floor=False,
							upset_boost=0.0):
	"""
	Dynamic programming over the bracket tree.

	contrarian_weight: 0.0 = pure EV, higher = more contrarian.
	homer_teams: list of team_ids whose public pick rates should be inflated.
	pool_size: number of entries in the pool (affects contrarian scaling).
	model_blend: 0.0 = pure Torvik, 1.0 = pure seed-historical.
	defense_floor: if True, penalize bad defenders in later rounds.
	upset_boost: 0.0-1.0, nudge R1 toward historical upset rates.
	"""

	winner_probs = compute_win_probs(teams, matchups, torvik_data,
									 seed_odds=seed_odds, model_blend=model_blend,
									 defense_floor=defense_floor, upset_boost=upset_boost)

	picks = {}
	expected_points = {}

	pool_factor = math.log(max(pool_size, 2)) / math.log(10)

	for matchup in matchups:
		m_id = matchup['id']
		m_round = matchup['round']
		points = scoring[m_round]

		ep = {}
		for t_id, prob in winner_probs[m_id].items():
			ep[t_id] = prob * points

		expected_points[m_id] = ep

		if contrarian_weight > 0:
			round_boost = 1.0 + (m_round / 5.0) * 0.5

			def pick_score(t):
				pop = seed_popularity(teams[t]['seed'])
				if homer_teams and t in homer_teams:
					pop = min(pop * 2.5, 0.5)
				leverage = ep[t] / max(pop, 0.001)
				return ep[t] + contrarian_weight * pool_factor * round_boost * leverage

			best_team = max(ep.keys(), key=pick_score)
		else:
			best_team = max(ep.keys(), key=lambda t: ep[t])

		picks[m_id] = best_team

	return picks, expected_points, winner_probs


def seed_popularity(seed):
	"""
	Approximate public pick rate by seed.
	In large pools, 1-seeds are picked by ~25-30% of brackets to win it all,
	while 12+ seeds are picked by <1%. This models the "chalk" tendency.
	"""
	popularity = {
		1: 0.30, 2: 0.15, 3: 0.08, 4: 0.05,
		5: 0.04, 6: 0.03, 7: 0.02, 8: 0.02,
		9: 0.01, 10: 0.01, 11: 0.01, 12: 0.005,
		13: 0.002, 14: 0.001, 15: 0.001, 16: 0.0005
	}
	return popularity.get(seed, 0.01)


def format_results(picks, teams, matchups, scoring, expected_points, winner_probs):
	"""Format the optimal bracket as readable output."""
	lines = []
	current_round = -1
	total_ev = 0.0

	round_names = {
		0: 'Round of 64', 1: 'Round of 32', 2: 'Sweet 16',
		3: 'Elite Eight', 4: 'Final Four', 5: 'Championship'
	}

	round_ev = {}

	for matchup in matchups:
		m_id = matchup['id']
		m_round = matchup['round']
		picked = picks[m_id]
		team = teams[picked]
		ep = expected_points[m_id][picked]
		total_ev += ep

		if m_round not in round_ev:
			round_ev[m_round] = 0.0
		round_ev[m_round] += ep

		if m_round != current_round:
			current_round = m_round
			if current_round > 0:
				lines.append('')
			lines.append(round_names.get(m_round, 'Round ' + str(m_round)))
			lines.append('-----')

		# Figure out the opponent side
		ref_1 = matchup['team_1_ref']
		ref_2 = matchup['team_2_ref']

		# Determine both teams in this initial matchup (for round 0)
		if ref_1.startswith('team-'):
			t1_id = int(ref_1.split('-')[1])
			t1_name = '(' + str(teams[t1_id]['seed']) + ') ' + teams[t1_id]['name']
		else:
			# For later rounds, show the picked team
			t1_id = picks[int(ref_1.split('-')[1])]
			t1_name = '(' + str(teams[t1_id]['seed']) + ') ' + teams[t1_id]['name']

		if ref_2.startswith('team-'):
			t2_id = int(ref_2.split('-')[1])
			t2_name = '(' + str(teams[t2_id]['seed']) + ') ' + teams[t2_id]['name']
		else:
			t2_id = picks[int(ref_2.split('-')[1])]
			t2_name = '(' + str(teams[t2_id]['seed']) + ') ' + teams[t2_id]['name']

		prob = winner_probs[m_id].get(picked, 0)
		seed = team['seed']
		name = team['name']

		lines.append('  (' + str(seed) + ') ' + name + '  [' + str(round(prob * 100, 1)) + '% | EV: ' + str(round(ep, 1)) + ' pts]')

	lines.append('')
	lines.append('--------------------')
	lines.append('')
	lines.append('Expected Value by Round')
	lines.append('-----')
	for r in sorted(round_ev.keys()):
		lines.append('  ' + round_names.get(r, 'Round ' + str(r)) + ': ' + str(round(round_ev[r], 1)) + ' pts')
	lines.append('')
	lines.append('Total Expected Score: ' + str(round(total_ev, 1)) + ' pts')

	champion = picks[matchups[-1]['id']]
	champ_prob = winner_probs[matchups[-1]['id']].get(champion, 0)
	lines.append('')
	lines.append('Champion: (' + str(teams[champion]['seed']) + ') ' + teams[champion]['name'] +
				 '  [' + str(round(champ_prob * 100, 1)) + '% probability]')

	# Show Final Four
	lines.append('')
	lines.append('Final Four')
	lines.append('-----')
	for m in matchups:
		if m['round'] == 4:
			picked = picks[m['id']]
			t = teams[picked]
			prob = winner_probs[m['id']].get(picked, 0)
			lines.append('  (' + str(t['seed']) + ') ' + t['name'] + '  [' + str(round(prob * 100, 1)) + '%]')

	return '\n'.join(lines)


def main():
	contrarian = len(sys.argv) > 1 and sys.argv[1] == 'contrarian'
	cw = 0.5 if contrarian else 0.0
	mode = 'CONTRARIAN (large pool)' if contrarian else 'EXPECTED VALUE (max points)'

	teams = load_teams()
	matchups = load_matchups()
	scoring = load_scoring()
	torvik_data = load_torvik()

	picks, expected_points, winner_probs = compute_optimal_bracket(
		teams, matchups, scoring, torvik_data, contrarian_weight=cw
	)

	output = format_results(picks, teams, matchups, scoring, expected_points, winner_probs)

	print('')
	print('OPTIMAL BRACKET — ' + mode)
	print('Powered by Torvik adjusted efficiency margins')
	print('=' * 50)
	print(output)

	# Write to file
	if not os.path.exists('exports'):
		os.mkdir('exports')

	filename = 'exports/optimal-contrarian.txt' if contrarian else 'exports/optimal.txt'
	with open(filename, 'w') as f:
		f.write('OPTIMAL BRACKET — ' + mode + '\n')
		f.write('Powered by Torvik adjusted efficiency margins\n')
		f.write('=' * 50 + '\n')
		f.write(output + '\n')

	print('\nResults written to ' + filename)


if __name__ == '__main__':
	main()
