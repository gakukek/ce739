// index.js
require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');

const aquariumController = require('./controllers/aquariumController');

const app = express();
app.use(bodyParser.json());

// Routes (implementasi sesuai spreadsheet)
app.post('/aquariums', aquariumController.createAquarium);
app.post('/aquariums/:id/feeding_settings', aquariumController.createFeedingSetting);
app.post('/aquariums/:id/feed', aquariumController.triggerFeed);

app.get('/aquariums', aquariumController.listAquariums);
app.get('/aquariums/:id', aquariumController.getAquarium);
app.get('/aquariums/:id/alerts', aquariumController.getAquariumAlerts);
app.get('/aquariums/:id/condition-history', aquariumController.getConditionHistory);
app.get('/aquariums/:id/daily-consumption', aquariumController.getDailyConsumption);
app.get('/aquariums/:id/feeding_settings', aquariumController.getFeedingSettings);

// Note: spreadsheet had PUT /aquarium/{id} (singular). We'll support both for safety:
app.put('/aquarium/:id', aquariumController.updateAquarium);   // singular path
app.put('/aquariums/:id', aquariumController.updateAquarium);  // plural path

app.put('/aquariums/:id/feeding_settings', aquariumController.updateFeedingSetting);
app.put('/aquariums/:id/alerts', aquariumController.updateAlertStatus);

app.delete('/aquariums/:id', aquariumController.deleteAquarium);
app.delete('/aquariums/:id/feeding_settings/:settingId', aquariumController.deleteFeedingSetting);

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Smart Aquarium API listening on port ${PORT}`);
});
