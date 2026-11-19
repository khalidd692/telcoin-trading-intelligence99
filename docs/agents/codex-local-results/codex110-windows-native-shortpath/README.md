Gestionnaire de tâches tasks.py

Utilisation :
  tasks.py --db CHEMIN COMMANDE [ARGUMENTS]

Commandes :
  add TITRE        Crée une tâche, affiche l'objet JSON créé.
  edit ID TITRE    Modifie le titre de la tâche ID, affiche l'objet JSON mis à jour.
  complete ID      Marque la tâche ID comme terminée, affiche l'objet JSON mis à jour.
  delete ID        Supprime la tâche ID, affiche l'objet JSON supprimé.
  list             Affiche la liste de toutes les tâches sous forme de tableau JSON.

Exemples avec la base demo.json :
tasks.py --db demo.json add "Acheter du lait"
tasks.py --db demo.json add "Lire un livre"
tasks.py --db demo.json list
tasks.py --db demo.json edit a1b2c3 "Acheter du pain"
tasks.py --db demo.json complete a1b2c3
