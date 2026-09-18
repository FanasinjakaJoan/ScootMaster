'use strict';

const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { config } = require('../config');
const { requireAuth } = require('../middleware/auth');

module.exports = function authRoutes(db) {
  const r = express.Router();

  /** POST /api/auth/login — identifie l'utilisateur et délivre un JWT. */
  r.post('/login', (req, res) => {
    const { username, password } = req.body || {};
    if (!username || !password) return res.status(400).json({ error: 'Identifiant et mot de passe requis.' });
    const user = db.prepare('SELECT * FROM users WHERE username = ? AND deleted_at IS NULL').get(String(username).trim());
    if (!user || !bcrypt.compareSync(String(password), user.password_hash)) {
      return res.status(401).json({ error: 'Identifiants incorrects.' });
    }
    const token = jwt.sign(
      { sub: user.id, username: user.username, role: user.role, fullName: user.full_name },
      config.jwtSecret,
      { expiresIn: config.jwtTtl }
    );
    res.json({
      token,
      user: { id: user.id, username: user.username, fullName: user.full_name, role: user.role },
    });
  });

  r.post('/logout', requireAuth, (req, res) => res.status(204).send());

  /** GET /api/auth/me — profil de l'utilisateur courant. */
  r.get('/me', requireAuth, (req, res) => {
    res.json({ user: req.user });
  });

  /**
   * POST /api/auth/refresh — renouvelle le jeton (session glissante).
   *
   * Accepte un jeton dont la signature est VALIDE même si la date d'expiration
   * est dépassée, tant qu'elle l'est depuis moins de `JWT_REFRESH_GRACE_DAYS`
   * jours (défaut 30). C'est ce qui garantit « session conservée jusqu'à la
   * déconnexion explicite » : l'app se réauthentifie silencieusement au retour
   * de l'utilisateur au lieu de le déconnecter d'office.
   *
   * À chaque refresh, le compte est re-vérifié en base : désactivé ou supprimé
   * ⇒ 401 immédiat (révocation effective). Codes d'erreur explicites :
   *   - TOKEN_INVALID : signature/masque invalide (vol ou secret changé) ;
   *   - TOKEN_EXPIRED : périmé au-delà de la fenêtre de grâce (reconnexion) ;
   *   - ACCOUNT_DISABLED : compte supprimé/désactivé.
   */
  r.post('/refresh', (req, res) => {
    const header = req.headers.authorization || '';
    const token = header.startsWith('Bearer ') ? header.slice(7) : null;
    if (!token) return res.status(401).json({ error: 'Authentification requise.', code: 'TOKEN_INVALID' });

    let payload;
    try {
      // Signature obligatoire ; l'expiration est contrôlée à la main ci-dessous
      // (fenêtre de grâce) au lieu d'être fatale comme dans requireAuth.
      payload = jwt.verify(token, config.jwtSecret, { ignoreExpiration: true });
    } catch {
      return res.status(401).json({ error: 'Jeton invalide — reconnexion requise.', code: 'TOKEN_INVALID' });
    }

    if (typeof payload.exp === 'number') {
      const lateMs = Date.now() - payload.exp * 1000;
      if (lateMs > config.jwtRefreshGraceDays * 24 * 60 * 60 * 1000) {
        return res.status(401).json({ error: 'Session trop ancienne — reconnexion requise.', code: 'TOKEN_EXPIRED' });
      }
    }

    const u = db.prepare('SELECT * FROM users WHERE id = ? AND deleted_at IS NULL').get(payload.sub);
    if (!u) {
      return res.status(401).json({ error: 'Compte introuvable ou désactivé — reconnexion requise.', code: 'ACCOUNT_DISABLED' });
    }
    const fresh = jwt.sign(
      { sub: u.id, username: u.username, role: u.role, fullName: u.full_name },
      config.jwtSecret,
      { expiresIn: config.jwtTtl }
    );
    res.json({
      token: fresh,
      user: { id: u.id, username: u.username, fullName: u.full_name, role: u.role },
    });
  });

  return r;
};
