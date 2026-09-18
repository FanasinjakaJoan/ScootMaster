# Correctif — « Votre session a expiré pendant la synchronisation »

Correctif complet pour **`FanasinjakaJoan/scoot-master-app`** : la session reste
maintenant active **jusqu'à la déconnexion explicite** de l'utilisateur.

> ⚠️ Ce dépôt (ScootMaster) sert uniquement de vecteur de livraison : le jeton
> GitHub de cette session n'a pas les droits d'écriture sur `scoot-master-app`.
> Appliquez le correctif en suivant l'une des 3 méthodes ci-dessous (2 minutes).

---

## Ce qui causait la déconnexion automatique

Après la connexion, l'app lance une **synchro automatique** (~0,5 s après le
login, puis à chaque retour sur l'app). Dans l'ancien code :

1. Si cette synchro recevait un **401 OU 403**, l'app **supprimait le jeton** et
   affichait « Votre session a expiré pendant la synchronisation… » — sans
   aucune tentative de récupération ;
2. **`/api/auth/refresh` refusait les jetons expirés** (il exigeait un jeton
   encore valide) : une session expirée était irrécupérable sans retaper le mot
   de passe ;
3. Le rafraîchissement n'était **qu'opportuniste** (si une synchro tombait par
   hasard dans les 5 min avant l'expiration) — aucun minuteur proactif ;
4. Un **403** (droits insuffisants, ou page de blocage de l'hébergeur type
   WAF/anti-bot) était traité comme une expiration de session → déconnexion
   abusive alors que l'utilisateur est authentifié.

## Ce que fait le correctif

| Fichier | Changement |
|---|---|
| `backend/src/routes/auth.js` | `/api/auth/refresh` accepte un jeton **périmé** dont la signature est valide, dans une fenêtre de grâce `JWT_REFRESH_GRACE_DAYS` (défaut **30 jours**). La révocation reste immédiate (compte désactivé/supprimé ⇒ 401). Codes explicites : `TOKEN_INVALID` / `TOKEN_EXPIRED` / `ACCOUNT_DISABLED` |
| `backend/src/config.js` | TTL du jeton porté à **7 jours** (par défaut) — glissant car renouvelé en silence ; ajout de `jwtRefreshGraceDays` |
| `backend/src/middleware/auth.js` | Codes d'erreur explicites sur les 401 |
| `mobile/src/store/AppStore.tsx` | Refresh silencieux **même sur jeton expiré** ; **minuteur proactif** qui renouvelle 5 min avant expiration (la session se prolonge toute seule tant que l'utilisateur ne se déconnecte pas) ; en cas de 401 pendant la synchro : **un refresh + un second cycle tentés avant toute déconnexion** |
| `mobile/src/data/sync/engine.ts` | Seul un **401** met fin à la session ; un **403** est journalisé (erreur), l'utilisateur reste connecté |
| `backend/tests/auth.test.js`, `mobile/__tests__/sync-auth.test.ts` | 6 nouveaux tests de refresh ; cas « 403 ne déconnecte pas » |

**Validation** : backend 41/41 tests OK · mobile 60/60 tests OK · TypeScript 0
erreur · build web + smoke test réel (login, synchro, navigation, écriture
serveur) OK · scénario bout-en-bout vérifié : jeton périmé → 401 → refresh
silencieux → synchro reprise **sans retaper le mot de passe**.

---

## Comment appliquer le correctif (sur un PC où vous avez accès au dépôt)

### Méthode A — avec le patch (recommandée, 4 commandes)

```bash
git clone https://github.com/FanasinjakaJoan/scoot-master-app.git
cd scoot-master-app
git checkout -b fix-session-persistante
git am /chemin/vers/scoot-master-app-session-fix.patch   # ce dossier
git push -u origin fix-session-persistante
```

Puis ouvrez la PR sur GitHub et fusionnez → le déploiement automatique (Render
autoDeploy / CI) mettra le correctif en ligne.

### Méthode B — copier les fichiers

Copiez le contenu de `fichiers_modifies/` par-dessus le dépôt
`scoot-master-app` (même arborescence), committez, poussez :

```bash
cp -r fichiers_modifies/* /chemin/vers/scoot-master-app/
cd /chemin/vers/scoot-master-app
git checkout -b fix-session-persistante && git add -A
git commit -m "fix(auth): session conservée jusqu'à la déconnexion explicite"
git push -u origin fix-session-persistante
```

### Méthode C — me donner les droits

Ajoutez le compte **`arena-ai-coding-agent[bot]`** comme collaborateur du dépôt
`scoot-master-app` (GitHub → Settings → Collaborators) et redemandez-le moi :
je pousserai la branche et ouvrirai la PR moi-même.

---

## Après le déploiement

1. **Rechargez l'app web** (Ctrl+Shift+R pour vider le cache) sur tous les
   appareils ;
2. Connectez-vous **une seule fois** : la session se renouvellera seule
   (refresh 5 min avant expiration, puis à chaque usage) ;
3. Si l'app a été installée comme PWA/APK, fermez-la complètement puis rouvrez-la.

Variables d'environnement utiles (facultatives, valeurs par défaut raisonnables) :

| Variable | Défaut | Rôle |
|---|---|---|
| `JWT_TTL` | `7d` | Durée du jeton d'accès (renouvelé en silence) |
| `JWT_REFRESH_GRACE_DAYS` | `30` | Durée pendant laquelle une session périmée reste récupérable sans mot de passe |
