'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { startTestServer, login, api } = require('./helpers');

test('auth : login, me, contrôle des rôles', async (t) => {
  const srv = await startTestServer();
  try {
    await t.test('login valide délivre un JWT', async () => {
      const { status, token, user } = await login(srv.base);
      assert.equal(status, 200);
      assert.ok(token);
      assert.equal(user.role, 'admin');
    });

    await t.test('login invalide renvoie 401', async () => {
      const { status } = await login(srv.base, 'admin', 'mauvais');
      assert.equal(status, 401);
    });

    await t.test('route protégée sans jeton → 401', async () => {
      const { status } = await api(srv.base, null, 'GET', '/api/bikes');
      assert.equal(status, 401);
    });

    await t.test('jeton invalide → 401', async () => {
      const { status } = await api(srv.base, 'abc.def.ghi', 'GET', '/api/bikes');
      assert.equal(status, 401);
    });

    await t.test('GET /api/auth/me renvoie le profil', async () => {
      const { token } = await login(srv.base);
      const { status, body } = await api(srv.base, token, 'GET', '/api/auth/me');
      assert.equal(status, 200);
      assert.equal(body.user.role, 'admin');
    });

    await t.test('suppression d\u2019une moto : vendeur refusé, admin accepté', async () => {
      const admin = await login(srv.base);
      const seller = await login(srv.base, 'vendeur', 'vendeur123');

      const created = await api(srv.base, admin.token, 'POST', '/api/bikes', {
        brand: 'Yamaha', model: 'Test 125', price: 1000000,
      });
      assert.equal(created.status, 201);
      const id = created.body.bike.id;

      const denied = await api(srv.base, seller.token, 'DELETE', `/api/bikes/${id}`);
      assert.equal(denied.status, 403);

      const ok = await api(srv.base, admin.token, 'DELETE', `/api/bikes/${id}`);
      assert.equal(ok.status, 200);

      const gone = await api(srv.base, admin.token, 'GET', `/api/bikes/${id}`);
      assert.equal(gone.status, 404);
    });
  } finally {
    await srv.close();
  }
});

// -------------------------------------------------------------------------
// Refresh de session : « session conservée jusqu'à la déconnexion »
// -------------------------------------------------------------------------
const jwt = require('jsonwebtoken');
const { config } = require('../src/config');

/** Signe un jeton de test avec un décalage d'expiration arbitraire. */
function signToken(userId, expiresIn) {
  return jwt.sign(
    { sub: userId, username: 'admin', role: 'admin', fullName: 'Admin' },
    config.jwtSecret,
    { expiresIn }
  );
}

test('auth : refresh silencieux — jeton périmé récupérable dans la fenêtre de grâce', async (t) => {
  const srv = await startTestServer();
  try {
    await t.test('jeton valide → refresh 200, nouveau jeton utilisable', async () => {
      const { token } = await login(srv.base);
      const res = await api(srv.base, token, 'POST', '/api/auth/refresh');
      assert.equal(res.status, 200);
      assert.ok(res.body.token);
      const me = await api(srv.base, res.body.token, 'GET', '/api/auth/me');
      assert.equal(me.status, 200);
    });

    await t.test('jeton expiré DEPUIS PEU → refresh 200 (session conservée)', async () => {
      const { user } = await login(srv.base);
      const late = signToken(user.id, '-2h'); // périmé depuis 2 h (< 30 j de grâce)
      const res = await api(srv.base, late, 'POST', '/api/auth/refresh');
      assert.equal(res.status, 200);
      assert.ok(res.body.token);
      const me = await api(srv.base, res.body.token, 'GET', '/api/auth/me');
      assert.equal(me.status, 200);
    });

    await t.test('jeton expiré AU-DELÀ de la grâce → 401 TOKEN_EXPIRED', async () => {
      const { user } = await login(srv.base);
      const ancient = signToken(user.id, '-60d'); // périmé depuis 60 j (> 30 j)
      const res = await api(srv.base, ancient, 'POST', '/api/auth/refresh');
      assert.equal(res.status, 401);
      assert.equal(res.body.code, 'TOKEN_EXPIRED');
    });

    await t.test('jeton falsifié → 401 TOKEN_INVALID', async () => {
      const res = await api(srv.base, signToken('x', '1h').slice(0, -2) + 'zz', 'POST', '/api/auth/refresh');
      assert.equal(res.status, 401);
      assert.equal(res.body.code, 'TOKEN_INVALID');
    });

    await t.test('compte supprimé → refresh refusé (révocation immédiate)', async () => {
      const { token, user } = await login(srv.base);
      srv.db.prepare('UPDATE users SET deleted_at = ? WHERE id = ?').run(new Date().toISOString(), user.id);
      const res = await api(srv.base, token, 'POST', '/api/auth/refresh');
      assert.equal(res.status, 401);
      assert.equal(res.body.code, 'ACCOUNT_DISABLED');
    });

    await t.test('sans jeton → 401', async () => {
      const res = await api(srv.base, null, 'POST', '/api/auth/refresh');
      assert.equal(res.status, 401);
    });
  } finally {
    await srv.close();
  }
});
