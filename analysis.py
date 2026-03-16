import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

df = pd.DataFrame(columns=['a_odds', 'b_sims', 'c_decay', 'd_picks', 'e_score', 'f_score_max'])

for i in ['seed', 'team', 'hybrid']:

	for j in range(1, 101):

		for k in [True, False]:
			group = i + '-' + str(j).zfill(2) + '-' + str(k)
			temp_df = pd.read_csv('exports/bulk_scored/' + group + '.csv')
			data = pd.DataFrame({
					'a_odds': [i],
					'b_sims': [j],
					'c_decay': [k],
					'd_picks': [temp_df.total_picks.median()],
					'e_score': [temp_df.total_score.median()],
					'f_score_max': [temp_df.total_score.max()]
				})
			df = df.append(data)

print(df.sort_values(['e_score', 'f_score_max'], ascending=[False, False]))