import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const USER = __ENV.K6_USERNAME || 'demo';
const PASS = __ENV.K6_PASSWORD || 'demo';
const SCENARIO = __ENV.SCENARIO || 'mixed';     
const RATE = Number(__ENV.RATE || 1);           
const DURATION = __ENV.DURATION || '30s';       
const TIME_UNIT = __ENV.TIME_UNIT || '1s';       
const MAX_VUS = Number(__ENV.MAX_VUS || 200);
const HEAVY_OP = __ENV.HEAVY_OP || 'summary';     

export const options = {
  scenarios: {
    [SCENARIO]: {
      executor: 'constant-arrival-rate',          
      exec: SCENARIO,
      rate: RATE,
      timeUnit: TIME_UNIT,
      duration: DURATION,
      preAllocatedVUs: Math.min(MAX_VUS, Math.max(10, RATE * 2)),
      maxVUs: MAX_VUS,
    },
  },
  
  thresholds: {
    'http_req_duration{phase:load}': ['p(95)<500'],
    'http_req_failed{phase:load}': ['rate<0.01'],
  },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'max'],
};


const PROFILE = [
  ['slots_free', 32],        
  ['appt_card', 15],         
  ['create', 12],            
  ['appt_list', 10],         
  ['specialists', 10],       
  ['services', 8],           
  ['specialists_search', 6], 
  ['cancel', 5],             
  ['summary', 2],            
];


const pick = (a) => a[Math.floor(Math.random() * a.length)];
const hdr = (t) => ({ Authorization: `Bearer ${t}`, Accept: 'application/json' });
const prm = (t, name, extra = {}) => ({ headers: hdr(t), tags: { phase: 'load', name }, ...extra });

const okOrConflict = http.expectedStatuses(200, 400, 404);

let myCreated = [];   

export function setup() {
  const login = http.post(`${BASE_URL}/auth/login`, { username: USER, password: PASS });
  if (login.status !== 200) throw new Error(`Вход не удался: ${login.status} ${login.body}`);
  const token = login.json('access_token');
  const get = (path) => http.get(`${BASE_URL}${path}`, { headers: hdr(token) }).json('items');

  const specialists = [...get('/specialists/?page=1&page_size=100'), ...get('/specialists/?page=2&page_size=100')];
  const services = get('/services/?page=1&page_size=100');
  const slots = [];                                  
  for (let p = 1; p <= 30; p++) slots.push(...get(`/slots/?page=${p}&page_size=100&status=free`));
  const active = [];                                 
  for (let p = 1; p <= 5; p++) active.push(...get(`/appointments/?page=${p}&page_size=100&status=active`));

  return {
    token,
    specialists: specialists.map((x) => x.id),
    services: services.map((x) => x.id),
    slots: slots.map((x) => x.id),
    active: active.map((x) => x.id),
  };
}


const OPS = {
  slots_free: (d) => {
    const r = http.get(`${BASE_URL}/slots/?specialist_id=${pick(d.specialists)}&status=free&page=1&page_size=20`,
      prm(d.token, 'GET /slots'));
    check(r, { 'slots 200': (x) => x.status === 200 });
  },
  appt_card: (d) => {
    const r = http.get(`${BASE_URL}/appointments/${pick(d.active)}`, prm(d.token, 'GET /appointments/{id}'));
    check(r, { 'card 200': (x) => x.status === 200 });
  },
  create: (d) => {
    const slot = d.slots[exec.scenario.iterationInTest % d.slots.length];
    const r = http.post(`${BASE_URL}/appointments/`,
      JSON.stringify({ slot_id: slot, service_id: pick(d.services), client_name: `k6 ${__VU}-${__ITER}` }),
      prm(d.token, 'POST /appointments', {
        headers: { ...hdr(d.token), 'Content-Type': 'application/json' },
        responseCallback: okOrConflict,
      }));
    if (r.status === 200) myCreated.push(r.json('id'));
  },
  appt_list: (d) => {
    const r = http.get(`${BASE_URL}/appointments/?page=${1 + Math.floor(Math.random() * 20)}&page_size=20`,
      prm(d.token, 'GET /appointments'));
    check(r, { 'list 200': (x) => x.status === 200 });
  },
  specialists: (d) => {
    const r = http.get(`${BASE_URL}/specialists/?page=${1 + Math.floor(Math.random() * 10)}&page_size=20`,
      prm(d.token, 'GET /specialists'));
    check(r, { 'specialists 200': (x) => x.status === 200 });
  },
  services: (d) => {
    const r = http.get(`${BASE_URL}/services/?page=1&page_size=30`, prm(d.token, 'GET /services'));
    check(r, { 'services 200': (x) => x.status === 200 });
  },
  specialists_search: (d) => {
    
    const term = encodeURIComponent(pick(['Специалист 000', 'Специалист 001', 'Специалист 012', 'Специалист 0150']));
    const r = http.get(`${BASE_URL}/specialists/?search=${term}&page=1&page_size=20`,
      prm(d.token, 'GET /specialists?search'));
    check(r, { 'search 200': (x) => x.status === 200 });
  },
  cancel: (d) => {
    const id = myCreated.length ? myCreated.pop() : pick(d.active);
    http.del(`${BASE_URL}/appointments/${id}`, null,
      prm(d.token, 'DELETE /appointments/{id}', { responseCallback: okOrConflict }));
  },
  summary: (d) => {
    const r = http.get(`${BASE_URL}/summary/?date_from=2026-01-01&date_to=2026-12-31`, prm(d.token, 'GET /summary'));
    check(r, { 'summary 200': (x) => x.status === 200 });
  },
};

function weighted() {
  let n = Math.random() * 100;
  for (const [name, w] of PROFILE) { if ((n -= w) < 0) return name; }
  return PROFILE[0][0];
}

export function mixed(d) { OPS[weighted()](d); }
export function heavy(d) { OPS[HEAVY_OP](d); }
