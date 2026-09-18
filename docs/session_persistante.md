# Session persistante — « garder la session jusqu'à la déconnexion »

Guide d'implémentation de référence pour corriger le comportement
« Votre session a expiré pendant la synchronisation » et faire en sorte que
**la session ne se termine jamais d'elle-même : elle se termine uniquement
quand l'utilisateur clique sur « Déconnexion »** (ou quand un administrateur
révoque la session).

Principe clé : la durée de vie d'une session ne doit pas être un minuteur
côté client ou serveur, mais un **état explicite** (connecté / déconnecté).

---

## 1. Les 5 règles à respecter

| # | Règle | Erreur classique qui cause l'expiration prématurée |
|---|-------|------------------------------------------------------|
| 1 | Émettre un **refresh token sans date d'expiration**, stocké côté serveur et révocable | Token unique avec `exp: 1h` : au bout d'une heure, « session expirée » |
| 2 | Renouveler l'access token **en silence** (automatiquement), sans intervention de l'utilisateur | L'app déconnecte dès le 401 au lieu de rafraîchir puis rejouer la requête |
| 3 | Ne purger la session locale **que** dans le gestionnaire de déconnexion explicite | Un intercepteur d'erreur vide le stockage local au moindre 401 réseau |
| 4 | Conserver les **modifications en attente** dans un stockage durable (IndexedDB / base locale) et les resynchroniser après reconnexion | La file d'attente vit en mémoire : toute déconnexion perd les données |
| 5 | La perte de réseau **n'est pas** une expiration de session | L'app confond « serveur injoignable » et « token invalide » → déconnexion abusive pendant la synchro |

---

## 2. Implémentation backend (exemple FastAPI / Python)

Deux jetons :
- **access token** : JWT court (15 min) — limite la fenêtre d'exploitation en cas de vol ;
- **refresh token** : chaîne aléatoire, **sans expiration**, stocké en base, révocable.

```python
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
import jwt  # PyJWT

app = FastAPI()
oauth2 = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

ACCESS_TTL = timedelta(minutes=15)   # court, mais renouvelé en silence
SECRET = "..."                       # chargez-le depuis l'environnement

def emettre_access_token(user_id: str) -> str:
    # Seul jeton avec une date d'expiration — il est toujours renouvelable.
    return jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + ACCESS_TTL},
        SECRET, algorithm="HS256")

def creer_session(user_id: str, con) -> str:
    # Refresh token SANS expiration : la session vit jusqu'à la déconnexion.
    token = secrets.token_urlsafe(48)
    con.execute("INSERT INTO sessions(token, user_id, cree_le) VALUES (?,?,?)",
                (token, user_id, datetime.now(timezone.utc)))
    con.commit()
    return token

def utilisateur_courant(token: str = Depends(oauth2)):
    if token is None:
        raise HTTPException(401, "non authentifié")
    try:  # access token expiré -> le client rafraîchit silencieusement
        return jwt.decode(token, SECRET, algorithms=["HS256"])["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "access_token_expire")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "jeton_invalide")

@app.post("/refresh")
def refresh(refresh_token: str, con=Depends(db)):
    row = con.execute("SELECT user_id FROM sessions WHERE token=?",
                      (refresh_token,)).fetchone()
    if row is None:
        raise HTTPException(401, "session_inconnue")  # déconnexion/révocation réelle
    # Rotation : l'ancien token devient inutilisable, un nouveau est émis.
    con.execute("DELETE FROM sessions WHERE token=?", (refresh_token,))
    nouveau = creer_session(row["user_id"], con)
    con.commit()
    return {"access_token": emettre_access_token(row["user_id"]),
            "refresh_token": nouveau}

@app.post("/logout")
def logout(refresh_token: str, con=Depends(db)):
    # SEUL point de sortie de la session (déconnexion explicite).
    con.execute("DELETE FROM sessions WHERE token=?", (refresh_token,))
    con.commit()
    return {"ok": True}
```

Aucun code ne supprime une session sur critère de temps : pas de `TTL`,
pas de cron de purge, pas d'`exp` sur le refresh token. La session ne meurt
que par `/logout` (ou révocation manuelle en base).

---

## 3. Implémentation client (web)

```javascript
// Stockage durable : localStorage survit à la fermeture du navigateur.
// (sessionStorage expirerait à la fermeture de l'onglet — ne pas l'utiliser.)
const stockage = localStorage;

async function api(chemin, options = {}, reassai = true) {
  options.headers = { ...options.headers,
    Authorization: `Bearer ${stockage.getItem("access_token")}` };
  const rep = await fetch(chemin, options);

  if (rep.status === 401 && reassai) {
    const r = await fetch("/refresh", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: stockage.getItem("refresh_token") }) });
    if (r.ok) {
      const t = await r.json();
      stockage.setItem("access_token", t.access_token);
      stockage.setItem("refresh_token", t.refresh_token); // rotation
      return api(chemin, options, false);                 // rejouer la requête
    }
    afficherBandeau("Reconnectez-vous — vos modifications en attente sont conservées sur cet appareil.");
    // IMPORTANT : ne PAS vider la file hors-ligne ni les brouillons ici.
    return rep; // laisser l'utilisateur se reconnecter quand il veut
  }
  return rep;
}

// Déconnexion explicite = le seul endroit où l'on purge la session.
async function deconnexion() {
  await fetch("/logout", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: stockage.getItem("refresh_token") }) });
  stockage.removeItem("access_token");
  stockage.removeItem("refresh_token");
  location.href = "/login";
}
```

File de synchronisation hors-ligne (règle 4) — écrire dans **IndexedDB**
(durable) et non en mémoire :

```javascript
async function mettreEnFile(operation) {         // appelée hors-ligne
  const db = await ouvrirIndexedDB("file_sync");
  await db.add("operations", { ...operation, horodatage: Date.now() });
}
async function resynchroniser() {                // au retour du réseau
  const db = await ouvrirIndexedDB("file_sync");
  for (const op of await db.getAll("operations")) {
    const rep = await api("/sync", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(op) });
    if (rep.ok) await db.delete("operations", op.id);
  }
}
addEventListener("online", resynchroniser);
```

---

## 4. Application mobile

- Stocker les jetons dans le stockage sécurisé (**Keychain** iOS /
  **Keystore** Android), jamais dans les préférences simples ni le code.
- Aucune invalidation automatique : ne pas écouter les événements de cycle
  de vie (mise en arrière-plan, veille) pour déconnecter.
- Déconnexion = bouton explicite → appel `/logout` → purge du Keychain.
- La file de synchronisation vit dans la base locale (SQLite/Room/Core Data)
  et survit à tout ; elle n'est vidée qu'après confirmation de réception
  serveur (`ack`) — même après une reconnexion.

---

## 5. Ce qu'il faut chercher dans le code existant pour trouver le coupable

1. `exp` / `expiresIn` / `maxAge` trop court sur le **refresh** token ou le cookie de session.
2. Un intercepteur qui fait `logout()` ou `clearStorage()` sur toute réponse `401/403`.
3. `sessionStorage` (au lieu de `localStorage`) ou cookie sans `Max-Age` (cookie de session navigateur).
4. Un cache/serveur intermédiaire (proxy, équilibreur de charge) avec timeout de session propre (ex. `session-timeout` Tomcat, `PHP session.gc_maxlifetime`).
5. Côté mobile : une économie de batterie ou un gestionnaire qui tue le process et vide les jetons en mémoire au lieu de les recharger depuis le stockage sécurisé.

---

## 6. Compromis de sécurité à connaître

Une session sans expiration augmente la fenêtre de risque si l'appareil est
volé. Atténuations compatibles avec l'exigence « jusqu'à la déconnexion » :

- refresh token **révocable** (liste en base) et **à rotation** à chaque usage ;
- lier la session à un empreinte d'appareil (user-agent + plateforme) et
  invalider sur changement brusque ;
- révocation distante possible (page « mes appareils » ou support) ;
- HTTPS obligatoire, access token court (15 min) pour limiter la portée d'un vol.
