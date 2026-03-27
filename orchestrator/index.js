const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const { exec } = require('child_process');
const path = require('path');
const redis = require('redis');
require('dotenv').config();

const app = express();
const server = http.createServer(app);
const io = new Server(server);
app.use(express.json());

const redisClient = redis.createClient({ url: process.env.REDIS_URL });
redisClient.connect();
redisClient.subscribe('tenant:*:events', (message) => {
  io.emit('agent_event', JSON.parse(message));
});

const agents = [
  { name: 'PM_Agent', needsInput: true },
  { name: 'Architect_Agent', needsInput: false },
  { name: 'UI_UX_Agent', needsInput: false },
  { name: 'Backend_Agent', needsInput: false },
  { name: 'Android_Agent', needsInput: false },
  { name: 'iOS_Agent', needsInput: false },
  { name: 'Windows_Agent', needsInput: false },
  { name: 'macOS_Agent', needsInput: false },
  { name: 'Linux_Agent', needsInput: false },
  { name: 'Database_Agent', needsInput: false },
  { name: 'QA_Agent', needsInput: false },
  { name: 'Security_Agent', needsInput: false },
  { name: 'Docs_Agent', needsInput: false },
  { name: 'Integration_Agent', needsInput: false },
  { name: 'Video_Agent', needsInput: false },
  { name: 'Analytics_Agent', needsInput: false },
  { name: 'Cloud_Architect_Agent', needsInput: false },
  { name: 'IaC_Agent', needsInput: false },
  { name: 'DevOps_Agent', needsInput: false },
  { name: 'Network_Security_Agent', needsInput: false },
  { name: 'Memory_Agent', needsInput: false },
  { name: 'Validation_Agent', needsInput: false },
  { name: 'Planner_Agent', needsInput: false },
  { name: 'Reviewer_Agent', needsInput: false },
  { name: 'FreeTierOrchestrator_Agent', needsInput: false },
  { name: 'Quantum_Agent', needsInput: false },
  { name: 'Blockchain_Agent', needsInput: false },
  { name: 'RPA_Agent', needsInput: false },
  { name: 'IoT_Agent', needsInput: false },
  { name: 'MLOps_Agent', needsInput: false },
];

async function runAgent(projectId, agent, userDesc = null) {
  return new Promise((resolve, reject) => {
    let command = `python3 agents_runner.py ${agent.name} ${projectId}`;
    if (agent.needsInput && userDesc) {
      command += ` "${userDesc.replace(/"/g, '\\"')}"`;
    }
    const timeout = 600000;
    const child = exec(command, { cwd: path.join(__dirname, '..'), timeout }, (error, stdout, stderr) => {
      if (error) reject(new Error(`${agent.name} failed: ${stderr || error.message}`));
      else resolve(stdout);
    });
    child.on('error', (err) => reject(err));
  });
}

app.post('/start', async (req, res) => {
  const { description } = req.body;
  if (!description) return res.status(400).json({ error: 'No description' });

  const projectId = Date.now().toString();
  io.emit('project_started', { projectId });

  try {
    for (let i = 0; i < agents.length; i++) {
      const agent = agents[i];
      await runAgent(projectId, agent, i === 0 ? description : null);
    }
    io.emit('project_completed', { projectId });
    res.json({ success: true, projectId });
  } catch (err) {
    io.emit('project_failed', { projectId, error: err.message });
    res.status(500).json({ error: err.message });
  }
});

app.get('/download/:projectId', async (req, res) => {
  const { projectId } = req.params;
  try {
    const key = `tenant:${projectId}:file:integration/integration_result.txt`;
    const content = await redisClient.get(key);
    if (!content) {
      return res.status(404).send('No output found for this project');
    }
    res.setHeader('Content-Type', 'application/octet-stream');
    res.setHeader('Content-Disposition', `attachment; filename="${projectId}_output.zip"`);
    res.send(content);
  } catch (err) {
    res.status(500).send('Error retrieving file');
  }
});

server.listen(3000, () => console.log('Orchestrator running on port 3000'));
