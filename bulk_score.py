import csv
import math
import os
import random
import sys


if not os.path.exists('exports'):
	os.mkdir('exports')

if not os.path.exists('exports/bulk_scored'):
	os.mkdir('exports/bulk_scored')

results = []

with open('data/results.csv', 'r', newline='') as infile:
	read = csv.reader(infile)
	next(read)

	for row in read:
		results.append(int(row[1]))

scoring = []

with open('data/scoring.csv', 'r', newline='') as infile:
	read = csv.reader(infile)
	next(read)

	for row in read:
		scoring.append(int(row[1]))

rounds = []

with open('data/matchups.csv', 'r', newline='') as infile:
	read = csv.reader(infile)
	next(read)

	for row in read:
		rounds.append(int(row[1]))

for i in ['seed', 'team', 'hybrid']:
	print(i)

	for j in range(1, 101):
		print(j)

		for k in [True, False]:
			group = i + '-' + str(j).zfill(2) + '-' + str(k)

			with open('exports/bulk/' + group + '.csv', 'r', newline='') as infile:

				with open('exports/bulk_scored/' + group + '.csv', 'w') as output:
					writer = csv.writer(output, lineterminator='\n')
					writer.writerow(['id', 'r0_picks', 'r0_score', 'r1_picks', 'r1_score', 'r2_picks', 'r2_score', 'r3_picks', 'r3_score', 'r4_picks', 'r4_score', 'r5_picks', 'r5_score', 'total_picks', 'total_score'])
					read = csv.reader(infile)
					next(read)

					for row in read:
						compare = list(map(int, row[1].split('-')[1:]))
						picks = [0, 0, 0, 0, 0, 0]
						score = [0, 0, 0, 0, 0, 0]
						total_picks = 0
						total_score = 0

						for l in range(0, 63):

							if compare[l] == results[l]:
								picks[rounds[l]] += 1
								total_picks += 1
								score[rounds[l]] += scoring[rounds[l]]
								total_score += scoring[rounds[l]]

						writer.writerow([row[0], picks[0], score[0], picks[1], score[1], picks[2], score[2], picks[3], score[3], picks[4], score[4], picks[5], score[5], total_picks, total_score])