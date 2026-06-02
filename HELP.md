lancer bdd : http://localhost:8000

lancer supervision : http://localhost:5000

package flask : pip install flask mysql-connector-python pyniryo

utiliser la simu : 

# Interface web en mode mock
USE_MOCK=1 python app.py

# Script standalone en mode mock
USE_MOCK=1 python main.py

# Mode normal (vrai robot)
python app.py
python main.py