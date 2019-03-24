import sys

from modules.functions import str_to_bool
from modules.functions import run_simulation
from modules.functions import write_results


if len(sys.argv) == 4:

	try:
		strategy = sys.argv[1]
		n = int(sys.argv[2])
		decay = str_to_bool(sys.argv[3])

	except:
		print('\nERROR: Input must be of format "' + sys.argv[0] + ' [seed|team|hybrid] [# of simulations per game] [true|false for chaotic decay]"\n')

	else:

		if strategy in ['seed', 'team', 'hybrid']:
			write_results(run_simulation(strategy, n, decay))

		else:
			print('\nERROR: Input must be of format "' + sys.argv[0] + ' [seed|team|hybrid] [# of simulations per game] [true|false for chaotic decay]"\n')

else:
	print('\nERROR: Input must be of format "' + sys.argv[0] + ' [seed|team|hybrid] [# of simulations per game] [true|false for chaotic decay]"\n')
