// controllers/aquariumController.js
const db = require('../db');
const format = require('pg-format');

// Helper: parse numeric safe
const toNumber = v => (v === null || v === undefined ? null : Number(v));

// 1. POST /aquariums
exports.createAquarium = async (req, res) => {
  try {
    const { user_id, name, size_litres } = req.body;
    if (!user_id || !name) return res.status(400).json({ error: 'user_id and name required' });

    const result = await db.query(
      `INSERT INTO aquariums (user_id, name, size_litres)
       VALUES ($1,$2,$3)
       RETURNING id, user_id, name, size_litres, created_at`,
      [user_id, name, size_litres]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    console.error('createAquarium', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 2. POST /aquariums/:id/feeding_settings
exports.createFeedingSetting = async (req, res) => {
  try {
    const aquariumId = req.params.id;
    const { name, type, interval_hours, feed_volume_grams, start_date, end_date, enabled } = req.body;

    if (!type) return res.status(400).json({ error: 'type required (interval|daily_times)' });

    const result = await db.query(
      `INSERT INTO schedules (device_id, name, type, interval_hours, feed_volume_grams, enabled, start_date, end_date)
       VALUES ($1,$2,$3,$4,$5,COALESCE($6,true),$7,$8)
       RETURNING id, device_id, name, type, interval_hours, feed_volume_grams, enabled, start_date, end_date`,
      [aquariumId, name || null, type, interval_hours || null, feed_volume_grams || null, enabled, start_date || null, end_date || null]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    console.error('createFeedingSetting', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 3. POST /aquariums/:id/feed
exports.triggerFeed = async (req, res) => {
  try {
    const aquariumId = req.params.id;
    const { volume_grams, actor } = req.body;
    const vol = toNumber(volume_grams) || null;

    const logRes = await db.query(
      `INSERT INTO feeding_logs (device_id, mode, volume_grams, actor)
       VALUES ($1,'MANUAL',$2,$3)
       RETURNING id, device_id, ts, mode, volume_grams, actor`,
      [aquariumId, vol, actor || 'user']
    );

    res.status(201).json({ status: 'success', feeding: logRes.rows[0] });
  } catch (err) {
    console.error('triggerFeed', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 4. GET /aquariums
exports.listAquariums = async (req, res) => {
  try {
    const userId = req.query.user_id;
    let q = 'SELECT id, user_id, name, size_litres, created_at FROM aquariums';
    const params = [];
    if (userId) {
      q += ' WHERE user_id = $1';
      params.push(userId);
    }
    const result = await db.query(q, params);
    res.json(result.rows);
  } catch (err) {
    console.error('listAquariums', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 5. GET /aquariums/:id
exports.getAquarium = async (req, res) => {
  try {
    const id = req.params.id;
    const aqu = await db.query('SELECT * FROM aquariums WHERE id = $1', [id]);
    if (aqu.rowCount === 0) return res.status(404).json({ error: 'not_found' });

    // Tidak perlu ambil devices karena sudah tidak ada tabel devices
    res.json(aqu.rows[0]);
  } catch (err) {
    console.error('getAquarium', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 6. GET /aquariums/:id/alerts
exports.getAquariumAlerts = async (req, res) => {
  try {
    const id = req.params.id;
    const result = await db.query(
      `SELECT * FROM alerts WHERE device_id = $1 ORDER BY ts DESC LIMIT 100`,
      [id]
    );
    res.json(result.rows);
  } catch (err) {
    console.error('getAquariumAlerts', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 7. GET /aquariums/:id/condition-history
exports.getConditionHistory = async (req, res) => {
  try {
    const id = req.params.id;
    const { start, end } = req.query;
    let q = `SELECT * FROM sensor_data WHERE device_id = $1`;
    const params = [id];

    if (start) {
      params.push(start);
      q += ` AND ts >= $${params.length}`;
    }
    if (end) {
      params.push(end);
      q += ` AND ts <= $${params.length}`;
    }
    q += ' ORDER BY ts DESC LIMIT 500';
    const result = await db.query(q, params);
    res.json(result.rows);
  } catch (err) {
    console.error('getConditionHistory', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 8. GET /aquariums/:id/daily-consumption
exports.getDailyConsumption = async (req, res) => {
  try {
    const id = req.params.id;
    const q = `
      SELECT date_trunc('day', ts) AS day,
             SUM(volume_grams) AS consumed
      FROM feeding_logs
      WHERE device_id = $1
      GROUP BY 1
      ORDER BY 1 DESC
      LIMIT 30
    `;
    const result = await db.query(q, [id]);
    res.json(result.rows.map(r => ({ date: r.day, consumed: Number(r.consumed) })));
  } catch (err) {
    console.error('getDailyConsumption', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 9. GET /aquariums/:id/feeding_settings
exports.getFeedingSettings = async (req, res) => {
  try {
    const id = req.params.id;
    const q = `SELECT * FROM schedules WHERE device_id = $1`;
    const result = await db.query(q, [id]);
    res.json(result.rows);
  } catch (err) {
    console.error('getFeedingSettings', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 10. PUT /aquarium/:id dan /aquariums/:id
exports.updateAquarium = async (req, res) => {
  try {
    const id = req.params.id;
    const { name, size_litres, feeding_volume_grams, feeding_period_hours } = req.body;
    const result = await db.query(
      `UPDATE aquariums
       SET name = COALESCE($1, name),
           size_litres = COALESCE($2, size_litres),
           feeding_volume_grams = COALESCE($3, feeding_volume_grams),
           feeding_period_hours = COALESCE($4, feeding_period_hours)
       WHERE id = $5
       RETURNING *`,
      [name, size_litres, feeding_volume_grams, feeding_period_hours, id]
    );
    if (result.rowCount === 0) return res.status(404).json({ error: 'not_found' });
    res.json(result.rows[0]);
  } catch (err) {
    console.error('updateAquarium', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 11. PUT /aquariums/:id/feeding_settings
exports.updateFeedingSetting = async (req, res) => {
  try {
    const aquariumId = req.params.id;
    const { settingId, name, type, interval_hours, feed_volume_grams, enabled, start_date, end_date } = req.body;
    if (!settingId) return res.status(400).json({ error: 'settingId required in body' });

    // pastikan setting ada di aquarium tersebut
    const check = await db.query(
      `SELECT * FROM schedules WHERE id = $1 AND device_id = $2`,
      [settingId, aquariumId]
    );
    if (check.rowCount === 0) return res.status(404).json({ error: 'schedule_not_found' });

    const upd = await db.query(
      `UPDATE schedules SET name = COALESCE($1,name), type = COALESCE($2,type),
        interval_hours = COALESCE($3,interval_hours),
        feed_volume_grams = COALESCE($4,feed_volume_grams),
        enabled = COALESCE($5,enabled),
        start_date = COALESCE($6,start_date),
        end_date = COALESCE($7,end_date)
        WHERE id = $8 RETURNING *`,
      [name, type, interval_hours, feed_volume_grams, enabled, start_date, end_date, settingId]
    );
    res.json(upd.rows[0]);
  } catch (err) {
    console.error('updateFeedingSetting', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 12. PUT /aquariums/:id/alerts
exports.updateAlertStatus = async (req, res) => {
  try {
    const aquariumId = req.params.id;
    const { alertId, resolved } = req.body;
    if (!alertId) return res.status(400).json({ error: 'alertId required' });

    const check = await db.query(
      `SELECT * FROM alerts WHERE id = $1 AND device_id = $2`,
      [alertId, aquariumId]
    );
    if (check.rowCount === 0) return res.status(404).json({ error: 'alert_not_found' });

    const upd = await db.query(
      `UPDATE alerts SET resolved = $1, resolved_at = CASE WHEN $1 THEN now() ELSE NULL END WHERE id = $2 RETURNING *`,
      [resolved === true || resolved === 'true', alertId]
    );
    res.json(upd.rows[0]);
  } catch (err) {
    console.error('updateAlertStatus', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 13. DELETE /aquariums/:id
exports.deleteAquarium = async (req, res) => {
  try {
    const id = req.params.id;
    const result = await db.query('DELETE FROM aquariums WHERE id = $1 RETURNING id', [id]);
    if (result.rowCount === 0) return res.status(404).json({ error: 'not_found' });
    res.json({ status: 'deleted', id: result.rows[0].id });
  } catch (err) {
    console.error('deleteAquarium', err);
    res.status(500).json({ error: 'internal_error' });
  }
};

// 14. DELETE /aquariums/:id/feeding_settings/:settingId
exports.deleteFeedingSetting = async (req, res) => {
  try {
    const aquariumId = req.params.id;
    const settingId = req.params.settingId;

    const check = await db.query(
      `SELECT * FROM schedules WHERE id = $1 AND device_id = $2`,
      [settingId, aquariumId]
    );
    if (check.rowCount === 0) return res.status(404).json({ error: 'schedule_not_found' });

    await db.query('DELETE FROM schedules WHERE id = $1', [settingId]);
    res.json({ status: 'deleted' });
  } catch (err) {
    console.error('deleteFeedingSetting', err);
    res.status(500).json({ error: 'internal_error' });
  }
};
