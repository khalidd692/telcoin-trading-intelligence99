# Synthetic task app
The Kilo free provider generated tasks.py. Six independent Docker behavior checks pass.
The original native mission remains FAIL because README.md was missing. This documentation was completed separately by the integrator; this is not proof of full autonomous delivery.
Run with Python 3:
python tasks.py --db demo.json add "Example task"
python tasks.py --db demo.json list
python tasks.py --db demo.json edit ID "Updated task"
python tasks.py --db demo.json complete ID
python tasks.py --db demo.json delete ID
IDs come from the add/list JSON. The program is a toy; no financial functionality.
