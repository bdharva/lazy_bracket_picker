"""
Web UI for the bracket optimizer.
Run: python app.py
Then open http://localhost:5050
"""

import json
import math
from flask import Flask, jsonify, request, Response

from optimize import (
	load_teams, load_matchups, load_scoring, load_torvik, load_seed_odds,
	compute_optimal_bracket, seed_popularity
)

app = Flask(__name__)

# Load data once at startup
TEAMS = load_teams()
MATCHUPS = load_matchups()
SCORING = load_scoring()
TORVIK = load_torvik()
SEED_ODDS = load_seed_odds()

ROUND_NAMES = {
	0: 'Round of 64', 1: 'Round of 32', 2: 'Sweet 16',
	3: 'Elite Eight', 4: 'Final Four', 5: 'Championship'
}

REGION_NAMES = {0: 'East', 1: 'West', 2: 'Midwest', 3: 'South'}


def summarize_bracket(picks, expected_points, winner_probs, chalk_picks=None):
	"""Extract summary info from a computed bracket."""
	total_ev = sum(expected_points[m['id']][picks[m['id']]] for m in MATCHUPS)

	# Early EV (R64 + R32) vs Late EV (S16+)
	early_ev = sum(expected_points[m['id']][picks[m['id']]] for m in MATCHUPS if m['round'] <= 1)
	late_ev = sum(expected_points[m['id']][picks[m['id']]] for m in MATCHUPS if m['round'] >= 2)

	# Pick divergence: how many picks differ from chalk (pure-EV) bracket
	if chalk_picks:
		divergence = sum(1 for m in MATCHUPS if picks[m['id']] != chalk_picks[m['id']])
	else:
		divergence = 0

	# Weighted divergence: late-round differences count more
	if chalk_picks:
		round_weights = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 5: 32}
		weighted_div = sum(round_weights.get(m['round'], 1) for m in MATCHUPS
						   if picks[m['id']] != chalk_picks[m['id']])
	else:
		weighted_div = 0

	# Differentiation score (legacy)
	diff_score = 0
	for m in MATCHUPS:
		picked = picks[m['id']]
		seed = TEAMS[picked]['seed']
		diff_score += seed * (1 + m['round'])
	diff_score /= len(MATCHUPS)

	# Champion
	champ_id = picks[MATCHUPS[-1]['id']]
	champ = TEAMS[champ_id]
	champ_prob = winner_probs[MATCHUPS[-1]['id']].get(champ_id, 0)

	# Final Four
	final_four = []
	for m in MATCHUPS:
		if m['round'] == 4:
			t = TEAMS[picks[m['id']]]
			final_four.append({
				'name': t['name'], 'seed': t['seed'],
				'prob': round(winner_probs[m['id']].get(picks[m['id']], 0) * 100, 1)
			})

	# Elite Eight
	elite_eight = []
	for m in MATCHUPS:
		if m['round'] == 3:
			t = TEAMS[picks[m['id']]]
			elite_eight.append({
				'name': t['name'], 'seed': t['seed'],
				'prob': round(winner_probs[m['id']].get(picks[m['id']], 0) * 100, 1)
			})

	# Full bracket by round
	full_bracket = {}
	for m in MATCHUPS:
		r = m['round']
		rname = ROUND_NAMES.get(r, 'Round ' + str(r))
		if rname not in full_bracket:
			full_bracket[rname] = []

		picked = picks[m['id']]
		t = TEAMS[picked]
		prob = winner_probs[m['id']].get(picked, 0)
		ep = expected_points[m['id']][picked]

		# Determine opponent
		ref_1 = m['team_1_ref']
		ref_2 = m['team_2_ref']
		if ref_1.startswith('team-'):
			t1_id = int(ref_1.split('-')[1])
		else:
			t1_id = picks[int(ref_1.split('-')[1])]
		if ref_2.startswith('team-'):
			t2_id = int(ref_2.split('-')[1])
		else:
			t2_id = picks[int(ref_2.split('-')[1])]

		opponent_id = t2_id if picked == t1_id else t1_id
		opponent = TEAMS[opponent_id]

		is_upset = t['seed'] > opponent['seed']

		full_bracket[rname].append({
			'pick': '(' + str(t['seed']) + ') ' + t['name'],
			'opponent': '(' + str(opponent['seed']) + ') ' + opponent['name'],
			'prob': round(prob * 100, 1),
			'ev': round(ep, 1),
			'upset': is_upset
		})

	# Upset count
	upset_count = 0
	for m in MATCHUPS:
		picked = picks[m['id']]
		ref_1 = m['team_1_ref']
		ref_2 = m['team_2_ref']
		if ref_1.startswith('team-'):
			t1_id = int(ref_1.split('-')[1])
		else:
			t1_id = picks[int(ref_1.split('-')[1])]
		if ref_2.startswith('team-'):
			t2_id = int(ref_2.split('-')[1])
		else:
			t2_id = picks[int(ref_2.split('-')[1])]
		if picked == t1_id and TEAMS[t1_id]['seed'] > TEAMS[t2_id]['seed']:
			upset_count += 1
		elif picked == t2_id and TEAMS[t2_id]['seed'] > TEAMS[t1_id]['seed']:
			upset_count += 1

	return {
		'total_ev': round(total_ev, 1),
		'early_ev': round(early_ev, 1),
		'late_ev': round(late_ev, 1),
		'diff_score': round(diff_score, 2),
		'divergence': divergence,
		'weighted_div': weighted_div,
		'champion': {'name': champ['name'], 'seed': champ['seed'],
					 'prob': round(champ_prob * 100, 1)},
		'final_four': final_four,
		'elite_eight': elite_eight,
		'full_bracket': full_bracket,
		'upset_count': upset_count
	}


@app.route('/api/teams')
def api_teams():
	team_list = [{'id': t['id'], 'name': t['name'], 'seed': t['seed']}
				 for t in sorted(TEAMS.values(), key=lambda x: (x['seed'], x['name']))]
	return jsonify(team_list)


@app.route('/api/generate', methods=['POST'])
def api_generate():
	data = request.json or {}
	pool_size = data.get('pool_size', 10)
	homer_ids = set(data.get('homer_teams', []))

	# First compute the chalk (pure-EV) bracket as reference
	chalk_picks, chalk_ep, chalk_wp = compute_optimal_bracket(
		TEAMS, MATCHUPS, SCORING, TORVIK,
		contrarian_weight=0.0,
		homer_teams=homer_ids if homer_ids else None,
		pool_size=pool_size,
		seed_odds=SEED_ODDS,
		model_blend=0.0,
		defense_floor=False,
		upset_boost=0.0
	)

	# Multi-dimensional parameter grid (tighter ranges for realistic results)
	contrarian_values = [0.0, 0.02, 0.05, 0.08, 0.12, 0.18, 0.25, 0.35, 0.5]
	blend_values = [0.0, 0.2, 0.5, 0.8]
	defense_values = [False, True]
	upset_values = [0.0, 0.3, 0.7]

	brackets = []
	seen_keys = set()
	idx = 0

	for cw in contrarian_values:
		for blend in blend_values:
			for defense in defense_values:
				for upset in upset_values:
					picks, ep, wp = compute_optimal_bracket(
						TEAMS, MATCHUPS, SCORING, TORVIK,
						contrarian_weight=cw,
						homer_teams=homer_ids if homer_ids else None,
						pool_size=pool_size,
						seed_odds=SEED_ODDS,
						model_blend=blend,
						defense_floor=defense,
						upset_boost=upset
					)
					summary = summarize_bracket(picks, ep, wp, chalk_picks=chalk_picks)

					# Deduplicate identical brackets
					dedup_key = str(summary['total_ev']) + '|' + str(summary['divergence']) + '|' + str(summary['late_ev'])
					if dedup_key in seen_keys:
						continue
					seen_keys.add(dedup_key)

					summary['id'] = idx
					summary['contrarian_weight'] = round(cw, 3)
					summary['model_blend'] = round(blend, 2)
					summary['defense_floor'] = defense
					summary['upset_boost'] = round(upset, 2)

					tags = []
					if cw > 0:
						tags.append('contrarian')
					if blend > 0:
						tags.append('seed-blend')
					if defense:
						tags.append('def-floor')
					if upset > 0:
						tags.append('upset-boost')
					summary['strategy_tags'] = tags if tags else ['pure-ev']

					brackets.append(summary)
					idx += 1

	# Filter out unrealistic brackets (historical range: 2-20 upsets per tournament)
	brackets = [b for b in brackets if b['upset_count'] <= 20]

	# Tag featured brackets
	if brackets:
		# Safest: highest total EV
		safest = max(brackets, key=lambda b: b['total_ev'])
		safest['featured'] = 'safest'

		# Riskiest: highest divergence (most picks from chalk)
		riskiest = max(brackets, key=lambda b: b['divergence'])
		riskiest['featured'] = 'riskiest'

		# Best balance: highest total EV among brackets with divergence >= median
		divs = sorted(b['divergence'] for b in brackets)
		med_div = divs[len(divs) // 2] if divs else 0
		mid_candidates = [b for b in brackets if b['divergence'] >= med_div and b.get('featured') is None]
		if mid_candidates:
			balanced = max(mid_candidates, key=lambda b: b['total_ev'])
			balanced['featured'] = 'balanced'

		# Sleeper: highest late-round EV among non-featured brackets
		sleeper_candidates = [b for b in brackets if b.get('featured') is None]
		if sleeper_candidates:
			sleeper = max(sleeper_candidates, key=lambda b: b['late_ev'])
			sleeper['featured'] = 'sleeper'

		# Historic: closest to historical upset norms (~12.7 avg) with best EV
		# Historical averages: R1: 6.1, R2: 3.7, S16: 1.7, E8: 0.5, F4: 0.2
		HIST_TARGET = 12.7
		historic_candidates = [b for b in brackets if b.get('featured') is None]
		if historic_candidates:
			historic = min(historic_candidates,
						   key=lambda b: abs(b['upset_count'] - HIST_TARGET) - b['total_ev'] * 0.001)
			historic['featured'] = 'historic'

	return jsonify(brackets)


@app.route('/')
def index():
	return Response(HTML, mimetype='text/html')


HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Lazy Bracket Optimizer</title>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
  [data-theme="dark"] {
    --bg: #1a1a1a;
    --surface: #232323;
    --surface2: #2c2c2c;
    --surface3: #363636;
    --border: rgba(160,145,125,0.14);
    --border-bright: rgba(160,145,125,0.28);
    --text: #ddd8d0;
    --text2: #888078;
    --text3: #585450;
    --amber: #b08050;
    --amber-dim: #906840;
    --amber-bright: #c89868;
    --cyan: #5aaa98;
    --cyan-dim: rgba(90,170,152,0.12);
    --red: #c86050;
    --red-dim: rgba(200,96,80,0.10);
    --blue: #6090c0;
    --purple: #9878b8;
    --plot-bg: rgba(35,35,35,0.5);
    --plot-grid: rgba(160,145,125,0.07);
    --hover-bg: #232323;
    --overlay-glow: rgba(160,145,125,0.06);
  }
  [data-theme="light"] {
    --bg: #edebe6;
    --surface: #f8f6f2;
    --surface2: #e6e3dc;
    --surface3: #dbd8d0;
    --border: rgba(100,90,75,0.14);
    --border-bright: rgba(100,90,75,0.25);
    --text: #2a2520;
    --text2: #706860;
    --text3: #a09888;
    --amber: #906838;
    --amber-dim: #785830;
    --amber-bright: #a87848;
    --cyan: #3a8878;
    --cyan-dim: rgba(58,136,120,0.10);
    --red: #a84838;
    --red-dim: rgba(168,72,56,0.08);
    --blue: #4870a0;
    --purple: #705898;
    --plot-bg: rgba(248,246,242,0.5);
    --plot-grid: rgba(100,90,75,0.07);
    --hover-bg: #f8f6f2;
    --overlay-glow: rgba(100,90,75,0.04);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'IBM Plex Mono', monospace;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    transition: background 0.3s, color 0.3s;
  }

  /* === HEADER === */
  .header {
    position: relative;
    padding: 16px 28px 14px;
    display: flex;
    align-items: center;
    gap: 16px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .header::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 28px;
    width: 100px;
    height: 1px;
    background: linear-gradient(90deg, var(--amber), transparent);
  }
  .logo {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .logo-icon {
    color: var(--amber);
    font-size: 16px;
    opacity: 0.7;
  }
  .header h1 {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -0.5px;
    color: var(--text);
  }
  .header h1 span {
    color: var(--amber);
    font-weight: 400;
  }
  .header-sub {
    font-size: 10px;
    color: var(--text3);
    letter-spacing: 1px;
  }
  .header-right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .theme-toggle {
    background: none;
    border: 1px solid var(--border);
    color: var(--text2);
    width: 32px;
    height: 32px;
    border-radius: 6px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  .theme-toggle:hover { border-color: var(--amber-dim); color: var(--amber); }

  /* === CONTROLS === */
  .controls {
    display: flex;
    gap: 16px;
    padding: 14px 32px;
    border-bottom: 1px solid var(--border);
    align-items: flex-end;
    flex-wrap: wrap;
    background: var(--surface);
  }
  .control-group {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .control-group > label {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--text2);
    font-weight: 500;
  }
  input[type="number"] {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 9px 14px;
    border-radius: 4px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    width: 110px;
    outline: none;
    transition: border-color 0.2s;
    height: 36px;
  }
  input[type="number"]:focus {
    border-color: var(--amber-dim);
  }

  /* homer select */
  .homer-select { position: relative; }
  .homer-trigger {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 9px 14px;
    border-radius: 4px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    cursor: pointer;
    min-width: 280px;
    height: 36px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: border-color 0.2s;
  }
  .homer-trigger:hover { border-color: var(--amber-dim); }
  .homer-trigger .arrow { color: var(--amber-dim); font-size: 10px; }
  .homer-dropdown {
    display: none;
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    background: var(--surface);
    border: 1px solid var(--border-bright);
    border-radius: 4px;
    max-height: 300px;
    overflow-y: auto;
    z-index: 100;
    box-shadow: 0 16px 48px rgba(0,0,0,0.5);
  }
  .homer-dropdown.open { display: block; }
  .homer-search {
    position: sticky;
    top: 0;
    background: var(--surface);
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    z-index: 1;
  }
  .homer-search input {
    width: 100%;
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 7px 10px;
    border-radius: 3px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    outline: none;
  }
  .homer-search input:focus { border-color: var(--amber-dim); }
  .homer-dropdown label {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 14px;
    cursor: pointer;
    font-size: 11px;
    text-transform: none;
    letter-spacing: 0;
    color: var(--text);
    transition: background 0.1s;
  }
  .homer-dropdown label:hover { background: var(--surface2); }
  .homer-dropdown label .seed-num { color: var(--text2); min-width: 20px; }
  .homer-dropdown input[type="checkbox"] {
    accent-color: var(--amber);
    width: 13px;
    height: 13px;
  }
  .homer-tags {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    max-width: 280px;
    margin-top: 4px;
  }
  .homer-tag {
    background: linear-gradient(135deg, var(--amber-dim), var(--amber));
    color: var(--bg);
    padding: 2px 10px;
    border-radius: 2px;
    font-size: 10px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
    font-family: 'Bricolage Grotesque', sans-serif;
    letter-spacing: 0.5px;
  }
  .homer-tag:hover { opacity: 0.7; }

  /* generate button */
  .btn-generate {
    position: relative;
    background: transparent;
    color: var(--amber);
    border: 1px solid var(--amber-dim);
    padding: 9px 28px;
    height: 36px;
    border-radius: 4px;
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    letter-spacing: 2px;
    text-transform: uppercase;
    transition: all 0.2s;
    overflow: hidden;
  }
  .btn-generate::before {
    content: '';
    position: absolute;
    inset: 0;
    background: var(--amber);
    opacity: 0;
    transition: opacity 0.2s;
    border-radius: inherit;
  }
  .btn-generate:hover { color: var(--bg); border-color: var(--amber); }
  .btn-generate:hover::before { opacity: 1; }
  .btn-generate span { position: relative; z-index: 1; }
  .btn-generate:disabled { opacity: 0.4; cursor: wait; }

  /* === MAIN LAYOUT === */
  .main {
    display: flex;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
  .chart-panel {
    flex: 1;
    padding: 12px 16px 16px;
    min-width: 0;
    position: relative;
    touch-action: pan-x pan-y;
  }
  .chart-panel::before {
    content: '';
    position: absolute;
    top: 12px;
    left: 16px;
    right: 16px;
    bottom: 16px;
    border: 1px solid var(--border);
    border-radius: 4px;
    pointer-events: none;
    z-index: 1;
  }

  /* === DETAIL PANEL === */
  .detail-panel {
    width: 400px;
    min-width: 400px;
    border-left: 1px solid var(--border);
    overflow-y: auto;
    overflow-x: hidden;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: linear-gradient(180deg, var(--surface) 0%, var(--bg) 100%);
  }
  .detail-panel.collapsed {
    width: 0;
    min-width: 0;
    border-left-color: transparent;
  }
  .detail-inner {
    padding: 24px 20px 80px;
    min-width: 400px;
    opacity: 1;
    transition: opacity 0.2s;
  }
  .detail-panel.collapsed .detail-inner { opacity: 0; }

  .detail-panel .section-label {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: var(--text2);
    margin: 24px 0 10px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .detail-panel .section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  /* champion card */
  .champ-card {
    position: relative;
    background: var(--surface2);
    border: 1px solid var(--border-bright);
    border-radius: 6px;
    padding: 24px 20px;
    text-align: center;
    overflow: hidden;
  }
  .champ-card::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 50% 0%, rgba(209,171,100,0.08) 0%, transparent 60%);
    pointer-events: none;
  }
  .champ-card .trophy {
    font-size: 24px;
    margin-bottom: 6px;
    color: var(--amber);
    opacity: 0.5;
  }
  .champ-card .seed-label {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 10px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--text2);
  }
  .champ-card .team-name {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.5px;
    color: var(--amber-bright);
    margin: 6px 0;
    text-transform: uppercase;
  }
  .champ-card .win-prob {
    font-size: 12px;
    color: var(--cyan);
    font-weight: 500;
  }

  /* stat pills */
  .stat-row {
    display: flex;
    gap: 8px;
    margin: 14px 0;
  }
  .stat-pill {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px 12px;
    text-align: center;
  }
  .stat-pill .stat-val {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 20px;
    font-weight: 700;
    color: var(--amber-bright);
  }
  .stat-pill .stat-val.upsets-val { color: var(--red); }
  .stat-pill .stat-label {
    font-size: 9px;
    color: var(--text2);
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-top: 2px;
  }

  /* team rows */
  .team-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 8px;
    border-radius: 3px;
    font-size: 12px;
    transition: background 0.1s;
  }
  .team-row:hover { background: var(--surface2); }
  .team-row .seed-num {
    color: var(--text3);
    font-size: 10px;
    min-width: 28px;
  }
  .team-row .team-name { color: var(--text); font-weight: 500; }
  .team-row .prob {
    color: var(--text2);
    font-size: 11px;
  }

  /* matchup rows */
  .round-section { margin-bottom: 4px; }
  .matchup-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 8px;
    font-size: 11px;
    border-left: 2px solid transparent;
    border-radius: 0 3px 3px 0;
    transition: all 0.1s;
    gap: 8px;
  }
  .matchup-row:hover { background: var(--surface2); }
  .matchup-row .matchup-teams { flex: 1; min-width: 0; }
  .matchup-row .pick {
    color: var(--cyan);
    font-weight: 500;
  }
  .matchup-row .vs {
    color: var(--text3);
    font-size: 9px;
    margin: 0 3px;
  }
  .matchup-row .loser { color: var(--text2); }
  .matchup-row .stats {
    color: var(--text3);
    font-size: 10px;
    white-space: nowrap;
    text-align: right;
  }

  /* upset styling */
  .matchup-row.upset {
    border-left-color: var(--red);
    background: var(--red-dim);
  }
  .matchup-row.upset .pick { color: var(--red); }
  .upset-flag {
    display: inline-block;
    background: var(--red);
    color: var(--bg);
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 7px;
    font-weight: 800;
    letter-spacing: 1.5px;
    padding: 1px 5px;
    border-radius: 2px;
    margin-left: 5px;
    vertical-align: middle;
    text-transform: uppercase;
  }

  /* === EMPTY STATE === */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    text-align: center;
    animation: fadeIn 0.6s ease;
  }
  .empty-bracket {
    width: 180px;
    height: 120px;
    margin-bottom: 24px;
    opacity: 0.3;
    color: var(--text2);
  }
  .empty-bracket svg {
    width: 100%;
    height: 100%;
  }
  .empty-state h2 {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 18px;
    font-weight: 600;
    color: var(--text2);
    margin-bottom: 8px;
  }
  .empty-state p {
    font-size: 12px;
    color: var(--text3);
    line-height: 1.8;
  }

  /* === SCROLLBAR === */
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb {
    background: var(--border-bright);
    border-radius: 3px;
  }

  /* === FILTER BAR === */
  .filter-bar {
    display: none;
    gap: 12px;
    padding: 10px 32px;
    border-bottom: 1px solid var(--border);
    align-items: center;
    flex-wrap: wrap;
    background: var(--bg);
  }
  .filter-bar.visible { display: flex; }
  .filter-bar .filter-label {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--text3);
    margin-right: 4px;
  }
  .filter-group {
    display: flex;
    align-items: center;
    gap: 6px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 4px 10px;
    cursor: pointer;
    user-select: none;
    transition: all 0.15s;
  }
  .filter-group:hover { border-color: var(--border-bright); }
  .filter-group.active {
    border-color: var(--amber-dim);
    background: rgba(209,171,100,0.08);
  }
  .filter-group .filter-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text3);
    transition: background 0.15s;
  }
  .filter-group.active .filter-dot { background: var(--amber); }
  .filter-group .filter-text {
    font-size: 10px;
    color: var(--text2);
    font-weight: 500;
  }
  .filter-group.active .filter-text { color: var(--text); }
  .filter-count {
    font-size: 10px;
    color: var(--text3);
    margin-left: auto;
    padding-left: 16px;
  }
  .filter-count strong { color: var(--amber-dim); }

  /* === FEATURED BAR === */
  .featured-bar {
    display: none;
    gap: 6px;
    padding: 8px 32px;
    align-items: center;
    border-bottom: 1px solid var(--border);
    background: var(--bg);
  }
  .featured-bar.visible { display: flex; }
  .featured-pill {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 5px 14px;
    border-radius: 4px;
    background: var(--surface2);
    border: 1px solid var(--border);
    cursor: pointer;
    transition: all 0.15s;
    flex: 1;
    min-width: 0;
  }
  .featured-pill:hover {
    border-color: var(--border-bright);
    background: var(--surface3);
  }
  .featured-pip {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .featured-pill .feat-label {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    white-space: nowrap;
  }
  .featured-pill .feat-detail {
    font-size: 9px;
    color: var(--text2);
    margin-left: auto;
    padding-left: 8px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .featured-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: 8px;
    cursor: pointer;
    user-select: none;
    flex-shrink: 0;
  }
  .featured-toggle .toggle-track {
    width: 32px;
    height: 16px;
    border-radius: 8px;
    background: var(--surface2);
    border: 1px solid var(--border);
    position: relative;
    transition: all 0.2s;
  }
  .featured-toggle.active .toggle-track {
    background: var(--amber-dim);
    border-color: var(--amber);
  }
  .toggle-track::after {
    content: '';
    position: absolute;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--text2);
    top: 2px;
    left: 2px;
    transition: all 0.2s;
  }
  .featured-toggle.active .toggle-track::after {
    left: 18px;
    background: var(--amber-bright);
  }
  .featured-toggle .toggle-label {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text2);
    white-space: nowrap;
  }

  /* === MOBILE === */
  @media (max-width: 768px) {
    body { height: 100dvh; }

    .header {
      padding: 12px 16px;
      flex-wrap: wrap;
      gap: 2px;
      background: linear-gradient(180deg, rgba(209,171,100,0.06) 0%, transparent 100%);
    }
    .header::after { left: 16px; width: 80px; }
    .logo-icon { font-size: 11px; }
    .header h1 { font-size: 16px; letter-spacing: -0.5px; }
    .header h1 span { font-size: 14px; letter-spacing: 1px; }
    .header-sub { display: none; }

    .controls {
      padding: 12px 16px;
      gap: 8px;
      display: grid;
      grid-template-columns: 1fr 1fr;
    }
    .control-group:nth-child(2) { grid-column: 1 / -1; }
    .control-group > label { font-size: 8px; letter-spacing: 1.5px; }
    input[type="number"] {
      width: 100%;
      height: 40px;
      font-size: 13px;
      border-radius: 6px;
    }
    .homer-trigger {
      min-width: 0;
      width: 100%;
      height: 40px;
      border-radius: 6px;
    }
    .btn-generate {
      width: 100%;
      height: 40px;
      border-radius: 6px;
      font-size: 11px;
    }

    .filter-bar {
      padding: 6px 16px;
      overflow-x: auto;
      flex-wrap: nowrap;
      -webkit-overflow-scrolling: touch;
      gap: 6px;
      scrollbar-width: none;
    }
    .filter-bar::-webkit-scrollbar { display: none; }
    .filter-bar .filter-label { display: none; }
    .filter-group {
      padding: 5px 10px;
      flex-shrink: 0;
      border-radius: 20px;
    }
    .filter-group .filter-dot { width: 6px; height: 6px; }
    .filter-group .filter-text { font-size: 9px; }
    .filter-count { display: none; }

    .featured-bar {
      padding: 6px 16px;
      overflow-x: auto;
      flex-wrap: nowrap;
      -webkit-overflow-scrolling: touch;
      gap: 6px;
      scrollbar-width: none;
    }
    .featured-bar::-webkit-scrollbar { display: none; }
    .featured-pill {
      flex: 0 0 auto;
      min-width: auto;
      padding: 7px 14px;
      border-radius: 20px;
    }
    .featured-pill .feat-detail { display: none; }
    .featured-pill .feat-label { font-size: 9px; }
    .featured-pill .featured-pip { width: 6px; height: 6px; }
    .featured-toggle .toggle-label { font-size: 8px; }

    .chart-panel {
      padding: 4px 8px 8px;
      flex: 1;
    }
    .chart-panel::before { display: none; }

    .detail-panel { display: none !important; }

    .homer-dropdown {
      position: fixed;
      top: auto;
      bottom: 0;
      left: 0;
      right: 0;
      max-height: 60vh;
      border-radius: 16px 16px 0 0;
      z-index: 200;
      box-shadow: 0 -8px 40px rgba(0,0,0,0.6);
    }
    .homer-dropdown label { padding: 10px 14px; font-size: 13px; }
    .homer-search input { height: 36px; font-size: 13px; }
  }

  /* === DETAIL OVERLAY === */
  .detail-overlay {
    display: none;
    position: fixed;
    inset: 0;
    z-index: 500;
    background: var(--bg);
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
  }
  .detail-overlay.open {
    display: flex;
    flex-direction: column;
    animation: overlayIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  }
  @keyframes overlayIn {
    from { opacity: 0; transform: translateY(40px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .detail-overlay .overlay-header {
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    height: 52px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    flex-shrink: 0;
  }
  .detail-overlay .overlay-header h2 {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 13px;
    font-weight: 600;
    color: var(--text2);
    text-transform: uppercase;
    letter-spacing: 2px;
  }
  .detail-overlay .overlay-close {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text2);
    width: 34px;
    height: 34px;
    border-radius: 50%;
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: inherit;
    transition: all 0.15s;
    -webkit-tap-highlight-color: transparent;
  }
  .detail-overlay .overlay-close:active {
    background: var(--surface3);
    transform: scale(0.92);
  }

  .detail-overlay .overlay-body {
    padding: 20px 16px 100px;
    flex: 1;
  }

  /* Overlay champion card — hero treatment */
  .detail-overlay .champ-card {
    padding: 28px 20px;
    border-radius: 12px;
    background: linear-gradient(160deg, var(--surface2) 0%, rgba(209,171,100,0.06) 100%);
    border: 1px solid var(--border-bright);
    position: relative;
    overflow: hidden;
  }
  .detail-overlay .champ-card::after {
    content: '';
    position: absolute;
    top: -60px;
    right: -40px;
    width: 160px;
    height: 160px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(209,171,100,0.1) 0%, transparent 70%);
    pointer-events: none;
  }
  .detail-overlay .champ-card .trophy { font-size: 30px; }
  .detail-overlay .champ-card .seed-label { font-size: 11px; letter-spacing: 4px; }
  .detail-overlay .champ-card .team-name { font-size: 28px; margin: 8px 0; }
  .detail-overlay .champ-card .win-prob { font-size: 14px; }

  /* Overlay stat pills */
  .detail-overlay .stat-row { gap: 6px; }
  .detail-overlay .stat-pill {
    border-radius: 8px;
    padding: 12px 8px;
  }
  .detail-overlay .stat-pill .stat-val { font-size: 18px; }
  .detail-overlay .stat-pill .stat-label { font-size: 8px; letter-spacing: 1.5px; }

  /* Overlay section labels */
  .detail-overlay .section-label {
    font-size: 10px;
    letter-spacing: 3px;
    margin: 28px 0 12px;
  }

  /* Overlay team rows */
  .detail-overlay .team-row {
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 13px;
    margin-bottom: 2px;
  }

  /* Overlay matchup rows */
  .detail-overlay .matchup-row {
    padding: 10px 12px;
    font-size: 12px;
    border-radius: 6px;
    margin-bottom: 2px;
  }
  .detail-overlay .matchup-row .stats { font-size: 11px; }
  .detail-overlay .matchup-row.upset {
    border-left-width: 3px;
    border-radius: 0 6px 6px 0;
  }
  .detail-overlay .upset-flag {
    font-size: 8px;
    padding: 2px 6px;
    border-radius: 3px;
  }

  /* Strategy tags in overlay */
  .detail-overlay [style*="display:inline-block"] {
    padding: 3px 10px !important;
    border-radius: 12px !important;
    font-size: 10px !important;
  }

  /* === ANIMATIONS === */
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes slideIn {
    from { opacity: 0; transform: translateX(20px); }
    to { opacity: 1; transform: translateX(0); }
  }
  .detail-inner > * {
    animation: slideIn 0.3s ease both;
  }
  .detail-inner > *:nth-child(1) { animation-delay: 0s; }
  .detail-inner > *:nth-child(2) { animation-delay: 0.03s; }
  .detail-inner > *:nth-child(3) { animation-delay: 0.06s; }
  .detail-inner > *:nth-child(4) { animation-delay: 0.09s; }
  .detail-inner > *:nth-child(5) { animation-delay: 0.12s; }
  .detail-inner > *:nth-child(6) { animation-delay: 0.15s; }
  .detail-inner > *:nth-child(7) { animation-delay: 0.18s; }
  .detail-inner > *:nth-child(8) { animation-delay: 0.21s; }
  .detail-inner > *:nth-child(9) { animation-delay: 0.24s; }
  .detail-inner > *:nth-child(10) { animation-delay: 0.27s; }
  .detail-inner > *:nth-child(n+11) { animation-delay: 0.3s; }
</style>
</head>
<body>

<div class="header">
  <div class="logo">
    <i class="fa-solid fa-basketball logo-icon"></i>
    <h1>Lazy Bracket <span>Optimizer</span></h1>
  </div>
  <span class="header-sub">Torvik AdjEM + Expected Value + Pool Strategy</span>
  <div class="header-right">
    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">
      <i class="fa-solid fa-circle-half-stroke"></i>
    </button>
  </div>
</div>

<div class="controls">
  <div class="control-group">
    <label>Pool Size</label>
    <input type="number" id="poolSize" value="25" min="2" max="10000">
  </div>
  <div class="control-group">
    <label>Homer Teams in Pool</label>
    <div class="homer-select" id="homerSelect">
      <div class="homer-trigger" id="homerTrigger">
        <span id="homerPlaceholder">Select teams...</span>
        <span class="arrow">&#9662;</span>
      </div>
      <div class="homer-dropdown" id="homerDropdown"></div>
    </div>
    <div class="homer-tags" id="homerTags" style="display:none"></div>
  </div>
  <div class="control-group">
    <label>&nbsp;</label>
    <button class="btn-generate" id="generateBtn" onclick="generate()"><span>Generate</span></button>
  </div>
</div>

<div class="filter-bar" id="filterBar">
  <span class="filter-label">Show</span>
  <div class="filter-group active" data-filter="pure-ev" onclick="toggleFilter(this)">
    <span class="filter-dot"></span>
    <span class="filter-text">Pure EV</span>
  </div>
  <div class="filter-group active" data-filter="contrarian" onclick="toggleFilter(this)">
    <span class="filter-dot"></span>
    <span class="filter-text">Contrarian</span>
  </div>
  <div class="filter-group active" data-filter="seed-blend" onclick="toggleFilter(this)">
    <span class="filter-dot"></span>
    <span class="filter-text">Seed Blend</span>
  </div>
  <div class="filter-group active" data-filter="def-floor" onclick="toggleFilter(this)">
    <span class="filter-dot"></span>
    <span class="filter-text">Def Floor</span>
  </div>
  <div class="filter-group active" data-filter="upset-boost" onclick="toggleFilter(this)">
    <span class="filter-dot"></span>
    <span class="filter-text">Upset Boost</span>
  </div>
  <span class="filter-count" id="filterCount"></span>
</div>

<div class="featured-bar" id="featuredBar"></div>

<div class="main">
  <div class="chart-panel" id="chartPanel">
    <div class="empty-state" id="emptyState">
      <div class="empty-bracket">
        <svg viewBox="0 0 180 120" fill="none" stroke="currentColor" stroke-width="1" opacity="0.5">
          <line x1="10" y1="10" x2="40" y2="10" stroke="currentColor"/>
          <line x1="10" y1="25" x2="40" y2="25" stroke="currentColor"/>
          <line x1="40" y1="10" x2="40" y2="25" stroke="currentColor"/>
          <line x1="40" y1="17" x2="70" y2="17" stroke="currentColor"/>
          <line x1="10" y1="40" x2="40" y2="40" stroke="currentColor"/>
          <line x1="10" y1="55" x2="40" y2="55" stroke="currentColor"/>
          <line x1="40" y1="40" x2="40" y2="55" stroke="currentColor"/>
          <line x1="40" y1="47" x2="70" y2="47" stroke="currentColor"/>
          <line x1="70" y1="17" x2="70" y2="47" stroke="currentColor"/>
          <line x1="70" y1="32" x2="100" y2="32" stroke="currentColor"/>
          <line x1="10" y1="70" x2="40" y2="70" stroke="currentColor"/>
          <line x1="10" y1="85" x2="40" y2="85" stroke="currentColor"/>
          <line x1="40" y1="70" x2="40" y2="85" stroke="currentColor"/>
          <line x1="40" y1="77" x2="70" y2="77" stroke="currentColor"/>
          <line x1="10" y1="100" x2="40" y2="100" stroke="currentColor"/>
          <line x1="10" y1="115" x2="40" y2="115" stroke="currentColor"/>
          <line x1="40" y1="100" x2="40" y2="115" stroke="currentColor"/>
          <line x1="40" y1="107" x2="70" y2="107" stroke="currentColor"/>
          <line x1="70" y1="77" x2="70" y2="107" stroke="currentColor"/>
          <line x1="70" y1="92" x2="100" y2="92" stroke="currentColor"/>
          <line x1="100" y1="32" x2="100" y2="92" stroke="currentColor"/>
          <line x1="100" y1="62" x2="130" y2="62" stroke="currentColor"/>
          <circle cx="135" cy="62" r="4" fill="currentColor" opacity="0.3" stroke="none"/>
        </svg>
      </div>
      <h2>Configure Your Pool</h2>
      <p>Set pool size, tag any homer teams,<br>then generate to explore optimal brackets.</p>
    </div>
    <div id="plotDiv" style="width:100%;height:100%;display:none;"></div>
  </div>
  <div class="detail-panel collapsed" id="detailPanel">
    <div class="detail-inner" id="detailContent"></div>
  </div>
</div>

<div class="detail-overlay" id="detailOverlay">
  <div class="overlay-header">
    <h2>Bracket Detail</h2>
    <button class="overlay-close" onclick="closeOverlay()">&times;</button>
  </div>
  <div class="overlay-body" id="overlayBody"></div>
</div>

<script>
let allBrackets = [];
let teams = [];
let featuredOnly = false;

function isMobile() { return window.innerWidth <= 768; }

function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  if (allBrackets.length > 0) renderChart();
}

// Restore saved theme
(function() {
  const saved = localStorage.getItem('theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
  else {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();

function closeOverlay() {
  document.getElementById('detailOverlay').classList.remove('open');
}

async function loadTeams() {
  const res = await fetch('/api/teams');
  teams = await res.json();
  const dd = document.getElementById('homerDropdown');
  dd.innerHTML = `<div class="homer-search"><input type="text" id="homerFilter" placeholder="Type to filter..." oninput="filterHomers(this.value)"></div>` +
    teams.map(t =>
      `<label data-name="${t.name.toLowerCase()}"><input type="checkbox" value="${t.id}" onchange="updateHomerTags()"><span class="seed-num">${t.seed}</span> ${t.name}</label>`
    ).join('');
}

document.getElementById('homerTrigger').addEventListener('click', e => {
  const dd = document.getElementById('homerDropdown');
  dd.classList.toggle('open');
  if (dd.classList.contains('open')) {
    setTimeout(() => { const f = document.getElementById('homerFilter'); if(f) f.focus(); }, 50);
  }
  e.stopPropagation();
});

function filterHomers(query) {
  const q = query.toLowerCase();
  document.querySelectorAll('#homerDropdown label[data-name]').forEach(lbl => {
    lbl.style.display = lbl.dataset.name.includes(q) ? '' : 'none';
  });
}
document.addEventListener('click', () => {
  document.getElementById('homerDropdown').classList.remove('open');
});
document.getElementById('homerDropdown').addEventListener('click', e => e.stopPropagation());

function getSelectedHomers() {
  return [...document.querySelectorAll('#homerDropdown input:checked')].map(cb => parseInt(cb.value));
}

function updateHomerTags() {
  const ids = getSelectedHomers();
  const tagsDiv = document.getElementById('homerTags');
  const placeholder = document.getElementById('homerPlaceholder');
  if (ids.length === 0) {
    tagsDiv.innerHTML = '';
    placeholder.textContent = 'Select teams...';
    return;
  }
  const names = ids.map(id => teams.find(x => x.id === id)?.name).filter(Boolean);
  placeholder.textContent = names.length <= 2 ? names.join(', ') : names.length + ' teams selected';
}

function removeHomer(id) {
  const cb = document.querySelector(`#homerDropdown input[value="${id}"]`);
  if (cb) cb.checked = false;
  updateHomerTags();
}

function getActiveFilters() {
  return [...document.querySelectorAll('.filter-group.active')].map(el => el.dataset.filter);
}

function toggleFilter(el) {
  el.classList.toggle('active');
  if (allBrackets.length > 0) renderChart();
}

function getFilteredBrackets() {
  let result = allBrackets;
  if (featuredOnly) {
    result = result.filter(b => b.featured);
  } else {
    const active = getActiveFilters();
    result = result.filter(b => b.strategy_tags.some(tag => active.includes(tag)));
  }
  return result;
}

function toggleFeaturedOnly() {
  featuredOnly = !featuredOnly;
  if (allBrackets.length > 0) renderChart();
}

async function generate() {
  const btn = document.getElementById('generateBtn');
  btn.disabled = true;
  btn.querySelector('span').textContent = 'Working...';

  const poolSize = parseInt(document.getElementById('poolSize').value) || 25;
  const homerTeams = getSelectedHomers();

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pool_size: poolSize, homer_teams: homerTeams})
    });
    allBrackets = await res.json();
    document.getElementById('filterBar').classList.add('visible');
    renderChart();
  } catch(e) {
    console.error(e);
  }

  btn.disabled = false;
  btn.querySelector('span').textContent = 'Generate';
}

function renderChart() {
  document.getElementById('emptyState').style.display = 'none';
  const plotDiv = document.getElementById('plotDiv');
  plotDiv.style.display = 'block';

  const cs = getComputedStyle(document.documentElement);

  // Compute axis ranges from ALL brackets so scales stay fixed when filtering
  const allEarly = allBrackets.map(b => b.early_ev);
  const allLate = allBrackets.map(b => b.late_ev);
  const pad = 15;
  const axisRanges = {
    x: [Math.min(...allEarly) - pad, Math.max(...allEarly) + pad],
    y: [Math.min(...allLate) - pad, Math.max(...allLate) + pad]
  };

  const filtered = getFilteredBrackets();

  // Update count
  document.getElementById('filterCount').innerHTML =
    `<strong>${filtered.length}</strong> / ${allBrackets.length} brackets`;

  if (filtered.length === 0) {
    Plotly.purge(plotDiv);
    return;
  }

  // Color by dominant strategy
  const tagColors = {
    'pure-ev': '#6090c0',
    'contrarian': '#e85d5d',
    'seed-blend': '#d1ab64',
    'def-floor': '#4dd8c0',
    'upset-boost': '#c084fc'
  };

  // X = Early EV (safe points), Y = Late EV (upside points)
  // This creates genuine 2D spread: defense-floor brackets shift late EV,
  // upset-boost shifts early EV, contrarian affects both differently
  const x = filtered.map(b => b.early_ev);
  const y = filtered.map(b => b.late_ev);
  // Size = total EV (bigger = higher scoring bracket)
  const evMin = Math.min(...filtered.map(b => b.total_ev));
  const evMax = Math.max(...filtered.map(b => b.total_ev));
  const evRange = evMax - evMin || 1;
  const sizes = filtered.map(b => 8 + ((b.total_ev - evMin) / evRange) * 28);
  // Color = divergence from chalk (green=chalk, red=chaos)
  const colors = filtered.map(b => b.divergence);

  const hoverText = filtered.map(b => {
    const f4 = b.final_four.map(t => `(${t.seed}) ${t.name}  ${t.prob}%`).join('<br>');
    const e8 = b.elite_eight.map(t => `(${t.seed}) ${t.name}`).join('<br>');
    const tags = b.strategy_tags.join(', ');
    return `<b>Champion: (${b.champion.seed}) ${b.champion.name}</b>  ${b.champion.prob}%` +
      `<br><br><b>Final Four</b><br>${f4}` +
      `<br><br><b>Elite Eight</b><br>${e8}` +
      `<br><br>Total: ${b.total_ev}  |  Early: ${b.early_ev}  |  Late: ${b.late_ev}` +
      `<br>Picks from chalk: ${b.divergence}  |  Upsets: ${b.upset_count}` +
      `<br>Strategy: ${tags}`;
  });

  const customData = filtered.map((b, i) => i);

  const trace = {
    x, y,
    mode: 'markers',
    type: 'scatter',
    marker: {
      size: sizes,
      color: colors,
      colorscale: [
        [0, '#4dd8c0'],
        [0.3, '#d1ab64'],
        [0.6, '#e88a5d'],
        [1, '#e85d5d']
      ],
      colorbar: {
        title: {text: 'Chalk \u2190\u2192 Chaos', font: {family: 'Bricolage Grotesque, sans-serif', size: 10, color: cs.getPropertyValue('--text2').trim()}, side: 'bottom'},
        tickfont: {family: 'IBM Plex Mono, monospace', size: 9, color: cs.getPropertyValue('--text3').trim()},
        thickness: 8,
        len: 0.35,
        x: 0.22,
        xanchor: 'center',
        y: 0.02,
        yanchor: 'bottom',
        orientation: 'h',
        bgcolor: 'rgba(0,0,0,0)',
        borderwidth: 0,
        outlinewidth: 0
      },
      line: {width: 1, color: cs.getPropertyValue('--border').trim()},
      opacity: 0.7
    },
    text: hoverText,
    hoverinfo: isMobile() ? 'none' : 'text',
    hoverlabel: {
      bgcolor: cs.getPropertyValue('--hover-bg').trim(),
      bordercolor: cs.getPropertyValue('--border-bright').trim(),
      font: {family: 'IBM Plex Mono, monospace', size: 11, color: cs.getPropertyValue('--text').trim()}
    },
    customdata: customData
  };

  const layout = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: cs.getPropertyValue('--plot-bg').trim(),
    font: {family: 'IBM Plex Mono, monospace', color: cs.getPropertyValue('--text3').trim()},
    xaxis: {
      title: {text: 'Early Rounds EV (R64 + R32)', font: {family: 'Bricolage Grotesque, sans-serif', size: 11, color: cs.getPropertyValue('--text2').trim()}},
      gridcolor: cs.getPropertyValue('--plot-grid').trim(),
      zerolinecolor: cs.getPropertyValue('--plot-grid').trim(),
      tickfont: {size: 10},
      range: axisRanges.x
    },
    yaxis: {
      title: {text: 'Late Rounds EV (S16 through Championship)', font: {family: 'Bricolage Grotesque, sans-serif', size: 11, color: cs.getPropertyValue('--text2').trim()}},
      gridcolor: cs.getPropertyValue('--plot-grid').trim(),
      zerolinecolor: cs.getPropertyValue('--plot-grid').trim(),
      tickfont: {size: 10},
      range: axisRanges.y
    },
    margin: {l: 56, r: 16, t: 16, b: 60},
    hovermode: 'closest'
  };

  // Build featured bar
  const featMeta = {
    safest:   {color: '#4dd8c0', label: 'Safest',    desc: 'Highest EV'},
    historic: {color: '#8b90a5', label: 'Historic',   desc: 'Norm upsets'},
    balanced: {color: '#d1ab64', label: 'Balanced',   desc: 'Best of both'},
    sleeper:  {color: '#6090c0', label: 'Sleeper',    desc: 'Late upside'},
    riskiest: {color: '#e85d5d', label: 'Riskiest',   desc: 'Max chaos'}
  };

  const featuredBrackets = {};
  filtered.forEach((b, i) => {
    if (b.featured && featMeta[b.featured]) {
      featuredBrackets[b.featured] = {bracket: b, idx: i};
    }
  });

  const bar = document.getElementById('featuredBar');
  let barHtml = '';
  for (const [key, meta] of Object.entries(featMeta)) {
    const fb = featuredBrackets[key];
    if (!fb) continue;
    const b = fb.bracket;
    barHtml += `<div class="featured-pill" onclick="showDetail(document.getElementById('plotDiv')._filteredBrackets[${fb.idx}])" style="color:${meta.color}">
      <span class="featured-pip" style="background:${meta.color}"></span>
      <span class="feat-label">${meta.label}</span>
      <span class="feat-detail">(${b.champion.seed}) ${b.champion.name} &middot; ${b.total_ev}ev &middot; ${b.upset_count}u</span>
    </div>`;
  }
  barHtml += `<div class="featured-toggle ${featuredOnly ? 'active' : ''}" onclick="toggleFeaturedOnly()">
    <div class="toggle-track"></div>
    <span class="toggle-label">Only These</span>
  </div>`;
  bar.innerHTML = barHtml;
  bar.classList.add('visible');

  // Add annotations for featured brackets on the plot
  const annotations = [];
  const arrowDirs = {safest: [0, -35], historic: [0, -35], balanced: [0, -35], sleeper: [0, -35], riskiest: [0, -35]};
  filtered.forEach(b => {
    if (b.featured && featMeta[b.featured]) {
      const m = featMeta[b.featured];
      const dirs = arrowDirs[b.featured] || [0, -30];
      annotations.push({
        x: b.early_ev,
        y: b.late_ev,
        text: m.label.toUpperCase(),
        font: {family: 'Bricolage Grotesque, sans-serif', size: 9, color: m.color},
        showarrow: true,
        arrowhead: 0,
        arrowwidth: 1.5,
        arrowcolor: m.color,
        ax: dirs[0],
        ay: dirs[1],
        bgcolor: cs.getPropertyValue('--bg').trim(),
        bordercolor: m.color,
        borderwidth: 1,
        borderpad: 3
      });
    }
  });
  layout.annotations = annotations;

  Plotly.newPlot(plotDiv, [trace], layout, {responsive: true, displayModeBar: false});
  plotDiv._filteredBrackets = filtered;

  plotDiv.on('plotly_click', function(data) {
    if (data.points.length > 0) {
      const idx = data.points[0].customdata;
      showDetail(plotDiv._filteredBrackets[idx]);
    }
  });
}

function showDetail(bracket) {
  const panel = document.getElementById('detailPanel');
  panel.classList.remove('collapsed');
  const mobile = isMobile();

  const tagColorMap = {
    'pure-ev': '#6090c0', 'contrarian': '#e85d5d',
    'seed-blend': '#d1ab64', 'def-floor': '#4dd8c0', 'upset-boost': '#c084fc'
  };
  const tagsHtml = (bracket.strategy_tags || []).map(tag =>
    `<span style="display:inline-block;background:${tagColorMap[tag]||'#555'};color:#fff;padding:2px 8px;border-radius:2px;font-size:9px;font-family:Bricolage Grotesque,sans-serif;font-weight:700;letter-spacing:1px;text-transform:uppercase">${tag}</span>`
  ).join(' ');

  let html = `
    <div class="champ-card">
      <div class="trophy"><i class="fa-solid fa-trophy"></i></div>
      <div class="seed-label">${bracket.champion.seed}-seed</div>
      <div class="team-name">${bracket.champion.name}</div>
      <div class="win-prob"><i class="fa-solid fa-bullseye" style="margin-right:4px;font-size:10px;opacity:0.6"></i>${bracket.champion.prob}% to win it all</div>
    </div>
    <div style="display:flex;gap:4px;flex-wrap:wrap;margin:10px 0 4px">${tagsHtml}</div>
    <div class="stat-row">
      <div class="stat-pill">
        <div class="stat-val">${bracket.total_ev}</div>
        <div class="stat-label">Total EV</div>
      </div>
      <div class="stat-pill">
        <div class="stat-val">${bracket.early_ev}</div>
        <div class="stat-label">Early EV</div>
      </div>
      <div class="stat-pill">
        <div class="stat-val">${bracket.late_ev}</div>
        <div class="stat-label">Late EV</div>
      </div>
    </div>
    <div class="stat-row">
      <div class="stat-pill">
        <div class="stat-val upsets-val">${bracket.upset_count}</div>
        <div class="stat-label">Upsets</div>
      </div>
      <div class="stat-pill">
        <div class="stat-val">${bracket.divergence}</div>
        <div class="stat-label">Picks from Chalk</div>
      </div>
    </div>
  `;

  html += '<div class="section-label">Final Four</div>';
  bracket.final_four.forEach(t => {
    html += `<div class="team-row">
      <span><span class="seed-num">(${t.seed})</span> <span class="team-name">${t.name}</span></span>
      <span class="prob">${t.prob}%</span>
    </div>`;
  });

  html += '<div class="section-label">Elite Eight</div>';
  bracket.elite_eight.forEach(t => {
    html += `<div class="team-row">
      <span><span class="seed-num">(${t.seed})</span> <span class="team-name">${t.name}</span></span>
      <span class="prob">${t.prob}%</span>
    </div>`;
  });

  const roundOrder = ['Round of 64','Round of 32','Sweet 16','Elite Eight','Final Four','Championship'];
  for (const rname of roundOrder) {
    const games = bracket.full_bracket[rname];
    if (!games) continue;
    html += `<div class="section-label">${rname}</div><div class="round-section">`;
    games.forEach(g => {
      const cls = g.upset ? 'matchup-row upset' : 'matchup-row';
      const flag = '';
      html += `<div class="${cls}">
        <span class="matchup-teams"><span class="pick">${g.pick}</span>${flag}<span class="vs">over</span><span class="loser">${g.opponent}</span></span>
        <span class="stats">${g.prob}%&ensp;${g.ev}ev</span>
      </div>`;
    });
    html += '</div>';
  }

  if (mobile) {
    document.getElementById('overlayBody').innerHTML = html;
    document.getElementById('detailOverlay').classList.add('open');
  } else {
    document.getElementById('detailContent').innerHTML = html;
    setTimeout(() => Plotly.Plots.resize(document.getElementById('plotDiv')), 300);
  }
}

loadTeams();

// Resize chart on orientation change / window resize
window.addEventListener('resize', () => {
  const plotDiv = document.getElementById('plotDiv');
  if (plotDiv && plotDiv.style.display !== 'none') {
    Plotly.Plots.resize(plotDiv);
  }
});
</script>
</body>
</html>
"""

if __name__ == '__main__':
	print('\n  Lazy Bracket Optimizer')
	print('  http://localhost:5050\n')
	app.run(port=5050, debug=True)
