const dayInput = document.getElementById('day');
const form = document.getElementById('trip-form');
const formMessage = document.getElementById('form-message');
const money = value => `${new Intl.NumberFormat('ru-RU').format(value)} ₸`;
const timeFormatter = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Asia/Almaty', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
});
const displayTime = iso => timeFormatter.format(new Date(iso));
const dateLabel = date => date.split('-').reverse().join('.');

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function setInitialFormDate(day) {
  document.getElementById('start').value = `${day}T08:00`;
  document.getElementById('end').value = `${day}T08:30`;
}

function showMessage(message, kind = '') {
  formMessage.textContent = message;
  formMessage.className = `form-message ${kind}`;
}

function tripRow(trip) {
  const item = document.createElement('div');
  item.className = 'trip';
  const icon = document.createElement('div');
  icon.className = `trip-icon ${trip.payment}`;
  icon.textContent = trip.payment === 'card' ? '▣' : '₸';
  const body = document.createElement('div');
  body.className = 'trip-body';
  const period = document.createElement('div');
  period.className = 'trip-time';
  period.textContent = `${displayTime(trip.start)}–${displayTime(trip.end)}`;
  const meta = document.createElement('div');
  meta.className = 'trip-meta';
  meta.textContent = `${trip.payment === 'card' ? 'Карта' : 'Наличные'} · ${trip.id}`;
  body.append(period, meta);
  const values = document.createElement('div');
  values.className = 'trip-values';
  const amount = document.createElement('div');
  amount.className = 'trip-amount';
  amount.textContent = money(trip.amount);
  const commission = document.createElement('div');
  commission.className = 'trip-commission';
  commission.textContent = `Комиссия −${money(trip.commission)}`;
  values.append(amount, commission);
  item.append(icon, body, values);
  return item;
}

async function loadDay() {
  const date = dayInput.value;
  if (!date) return;
  const tripsElement = document.getElementById('trips');
  try {
    const response = await fetch(`/api/days/${encodeURIComponent(date)}`);
    if (!response.ok) throw new Error('Не удалось загрузить сводку');
    const data = await response.json();
    const summary = data.summary;
    setText('display-date', dateLabel(date));
    setText('trip-count', summary.trip_count);
    setText('revenue', money(summary.revenue));
    setText('commission', `−${money(summary.commission)}`);
    setText('payment-breakdown', `${new Intl.NumberFormat('ru-RU').format(summary.cash)} / ${money(summary.card)}`);
    setText('net', money(summary.net));
    setText('revenue-card', money(summary.revenue));
    setText('net-card', money(summary.net));
    setText('rides-label', `${summary.trip_count} поездок`);
    tripsElement.className = 'trips-list';
    tripsElement.replaceChildren();
    if (!data.trips.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.innerHTML = '<strong>За этот день поездок нет</strong>Добавьте первую поездку справа.';
      tripsElement.append(empty);
    } else {
      data.trips.forEach(trip => tripsElement.append(tripRow(trip)));
    }
  } catch (error) {
    tripsElement.textContent = error.message;
    tripsElement.className = 'trips-list load-error';
  }
}

function shiftDay(amount) {
  // Use UTC date math to avoid shifting the calendar date based on browser timezone.
  const [year, month, day] = dayInput.value.split('-').map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + amount));
  dayInput.value = shifted.toISOString().slice(0, 10);
  setInitialFormDate(dayInput.value);
  loadDay();
}

document.getElementById('previous-day').addEventListener('click', () => shiftDay(-1));
document.getElementById('next-day').addEventListener('click', () => shiftDay(1));
dayInput.addEventListener('change', () => { setInitialFormDate(dayInput.value); loadDay(); });

form.addEventListener('submit', async event => {
  event.preventDefault();
  showMessage('');
  const button = document.getElementById('submit-trip');
  const fields = new FormData(form);
  const body = {
    id: fields.get('id').trim(),
    start: `${fields.get('start')}:00+05:00`,
    end: `${fields.get('end')}:00+05:00`,
    amount: Number(fields.get('amount')),
    payment: fields.get('payment'),
    commission: Number(fields.get('commission')),
  };
  button.disabled = true;
  try {
    const response = await fetch('/api/trips', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    const result = await response.json();
    if (!response.ok) {
      const text = typeof result.detail === 'string' ? result.detail : 'Проверьте сумму, время, комиссию и ID поездки';
      throw new Error(text);
    }
    const addedDay = body.start.slice(0, 10);
    dayInput.value = addedDay;
    setInitialFormDate(addedDay);
    await loadDay();
    showMessage(result.created ? 'Поездка сохранена.' : 'Такая поездка уже была сохранена — дубль не создан.', 'success');
  } catch (error) {
    showMessage(error.message, 'error');
  } finally {
    button.disabled = false;
  }
});

setInitialFormDate(dayInput.value);
loadDay();
