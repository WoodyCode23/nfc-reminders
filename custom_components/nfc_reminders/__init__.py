class NFCReminderCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._reminders = [];
  }

  setConfig(config) {
    if (!config.reminders || !Array.isArray(config.reminders)) {
      throw new Error('You must define reminders array');
    }
    this.config = config;
    this._reminders = config.reminders;
    this._groups = config.groups || [];
    this._useHomeAssistant = config.use_home_assistant_storage || false;
  }

  set hass(hass) {
    this._hass = hass;
    
    if (!this._subscribed) {
      this._subscribed = true;
      this._subscribeToEvents();
    }
    
    this.render();
  }

  _subscribeToEvents() {
    if (!this._hass) return;
    
    this._hass.connection.subscribeEvents((event) => {
      this._handleTagScanned(event);
    }, 'tag_scanned');
  }

  _handleTagScanned(event) {
    const tagId = event.data.tag_id;
    
    const group = this._groups.find(g => g.tag_id === tagId);
    if (group) {
      const timestamp = new Date().toISOString();
      group.reminder_names.forEach(name => {
        const reminder = this._reminders.find(r => r.name === name);
        if (reminder) {
          this._updateScanTime(reminder, timestamp);
        }
      });
      this.render();
      return;
    }
    
    const reminder = this._reminders.find(r => r.nfc_tag === tagId);
    if (reminder) {
      this._updateScanTime(reminder, new Date().toISOString());
      this.render();
    }
  }

  _updateScanTime(reminder, timestamp) {
    if (this._useHomeAssistant && reminder.entity_id && this._hass) {
      const dateObj = new Date(timestamp);
      const dateStr = dateObj.toISOString().slice(0, 19);
      
      this._hass.callService('input_datetime', 'set_datetime', {
        entity_id: reminder.entity_id,
        datetime: dateStr
      });
    } else {
      const storageKey = `nfc_reminder_${reminder.name}`;
      const scanData = {
        timestamp: timestamp,
        count: (this._getScanData(reminder.name).count || 0) + 1
      };
      localStorage.setItem(storageKey, JSON.stringify(scanData));
    }
  }

  _getScanData(reminderName) {
    const reminder = this._reminders.find(r => r.name === reminderName);
    
    if (this._useHomeAssistant && reminder && reminder.entity_id && this._hass) {
      const state = this._hass.states[reminder.entity_id];
      let person = null;
      
      if (reminder.person_entity_id) {
        const personState = this._hass.states[reminder.person_entity_id];
        if (personState && personState.state && personState.state !== 'unknown' && personState.state !== 'Unknown') {
          person = personState.state;
        }
      }
      
      if (state && state.state && state.state !== 'unknown') {
        return {
          timestamp: new Date(state.state),
          count: 0,
          person: person
        };
      }
    }
    
    const storageKey = `nfc_reminder_${reminderName}`;
    const data = localStorage.getItem(storageKey);
    if (!data) return { timestamp: null, count: 0, person: null };
    try {
      const parsed = JSON.parse(data);
      return {
        timestamp: parsed.timestamp ? new Date(parsed.timestamp) : null,
        count: parsed.count || 0,
        person: null
      };
    } catch {
      return { timestamp: null, count: 0, person: null };
    }
  }

  _getTimeSince(date) {
    if (!date) return 'Not scanned';
    
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    
    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    return 'Just now';
  }

  _formatDateTime(date) {
    if (!date) return '';
    
    const options = { 
      month: 'short', 
      day: 'numeric', 
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    };
    
    return date.toLocaleString('en-US', options);
  }

  _isOverdue(reminderName, interval, unit) {
    const scanData = this._getScanData(reminderName);
    if (!scanData.timestamp) return false;
    
    const now = new Date();
    const diff = now - scanData.timestamp;
    
    let threshold = 0;
    switch(unit) {
      case 'days':
        threshold = interval * 24 * 60 * 60 * 1000;
        break;
      case 'hours':
        threshold = interval * 60 * 60 * 1000;
        break;
      case 'minutes':
        threshold = interval * 60 * 1000;
        break;
    }
    
    return diff > threshold;
  }

  _getProgressPercentage(reminderName, interval, unit) {
    const scanData = this._getScanData(reminderName);
    if (!scanData.timestamp) return 0;
    
    const now = new Date();
    const diff = now - scanData.timestamp;
    
    let threshold = 0;
    switch(unit) {
      case 'days':
        threshold = interval * 24 * 60 * 60 * 1000;
        break;
      case 'hours':
        threshold = interval * 60 * 60 * 1000;
        break;
      case 'minutes':
        threshold = interval * 60 * 1000;
        break;
    }
    
    const percentage = Math.min((diff / threshold) * 100, 100);
    return Math.round(percentage);
  }

  render() {
    if (!this.config || !this._hass) return;

    this.shadowRoot.innerHTML = `
      <style>
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }
        
        :host {
          display: block;
        }
        
        .card {
          background: rgba(255, 255, 255, 0.07);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 12px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
          padding: 8px;
          backdrop-filter: blur(10px);
        }
        
        .reminders-list {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        
        .reminder {
          background: transparent;
          border-radius: 8px;
          padding: 10px 12px;
          transition: all 0.2s ease;
          display: flex;
          justify-content: space-between;
          align-items: center;
          min-height: 60px;
          border-left: 3px solid transparent;
        }
        
        .reminder:hover {
          background: rgba(255, 255, 255, 0.08);
        }
        
        .reminder.status-good {
          border-left-color: rgba(16, 185, 129, 0.6);
        }
        
        .reminder.status-good:hover {
          background: rgba(16, 185, 129, 0.12);
        }
        
        .reminder.status-warning {
          border-left-color: rgba(245, 158, 11, 0.6);
        }
        
        .reminder.status-warning:hover {
          background: rgba(245, 158, 11, 0.12);
        }
        
        .reminder.status-overdue {
          border-left-color: rgba(239, 68, 68, 0.7);
        }
        
        .reminder.status-overdue:hover {
          background: rgba(239, 68, 68, 0.15);
        }
        
        .reminder + .reminder {
          border-top: 1px solid rgba(255, 255, 255, 0.06);
        }
        
        .reminder-left {
          flex: 1;
        }
        
        .reminder-name {
          font-size: 15px;
          font-weight: 600;
          color: var(--primary-text-color);
          margin-bottom: 6px;
        }
        
        .reminder.status-good .reminder-name {
          color: rgba(16, 185, 129, 1);
        }
        
        .reminder.status-warning .reminder-name {
          color: rgba(245, 158, 11, 1);
        }
        
        .reminder.status-overdue .reminder-name {
          color: rgba(239, 68, 68, 1);
        }
        
        .reminder-info {
          display: flex;
          flex-direction: column;
          gap: 3px;
          font-size: 12px;
          color: var(--secondary-text-color);
          opacity: 0.85;
        }
        
        .info-row {
          display: flex;
          gap: 8px;
          align-items: center;
        }
        
        .status-text {
          font-weight: 500;
        }
        
        .person-text {
          font-style: italic;
          opacity: 0.7;
        }
        
        .datetime-text {
          font-size: 11px;
          opacity: 0.65;
        }
        
        .reminder-right {
          display: flex;
          align-items: center;
          margin-left: 12px;
        }
        
        .progress-circle {
          width: 42px;
          height: 42px;
          border-radius: 50%;
          background: conic-gradient(
            var(--progress-color) var(--progress-percent),
            rgba(255, 255, 255, 0.12) var(--progress-percent)
          );
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
        }
        
        .progress-circle::before {
          content: '';
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: var(--card-background-color, rgba(0, 0, 0, 0.3));
          position: absolute;
        }
        
        .progress-text {
          position: relative;
          z-index: 1;
          font-size: 11px;
          font-weight: 700;
          color: var(--primary-text-color);
        }
      </style>
      
      <div class="card">
        <div class="reminders-list">
          ${this._reminders.map(reminder => this._renderReminder(reminder)).join('')}
        </div>
      </div>
    `;
  }

  _getColorClass(progress) {
    if (progress < 50) return 'status-good';
    if (progress < 80) return 'status-warning';
    return 'status-overdue';
  }

  _getProgressColor(progress) {
    if (progress < 50) return 'rgba(16, 185, 129, 0.9)';
    if (progress < 80) return 'rgba(245, 158, 11, 0.9)';
    return 'rgba(239, 68, 68, 1)';
  }

  _renderReminder(reminder) {
    const scanData = this._getScanData(reminder.name);
    const timeSince = this._getTimeSince(scanData.timestamp);
    const formattedDateTime = this._formatDateTime(scanData.timestamp);
    const progress = this._getProgressPercentage(reminder.name, reminder.interval, reminder.unit);
    const colorClass = this._getColorClass(progress);
    const progressColor = this._getProgressColor(progress);
    const progressPercent = `${progress * 3.6}deg`;
    
    return `
      <div class="reminder ${colorClass}" style="--progress-color: ${progressColor}; --progress-percent: ${progressPercent};">
        <div class="reminder-left">
          <div class="reminder-name">${reminder.name}</div>
          <div class="reminder-info">
            <div class="info-row">
              <span class="status-text">${timeSince}</span>
              ${scanData.person ? `<span class="person-text">• by ${scanData.person}</span>` : ''}
            </div>
            ${formattedDateTime ? `<div class="datetime-text">${formattedDateTime}</div>` : ''}
          </div>
        </div>
        <div class="reminder-right">
          <div class="progress-circle">
            <span class="progress-text">${progress}%</span>
          </div>
        </div>
      </div>
    `;
  }

  getCardSize() {
    return 2;
  }

  static getStubConfig() {
    return {
      reminders: [
        {
          name: "Example Reminder",
          nfc_tag: "your_tag_id_here",
          interval: 5,
          unit: "days"
        }
      ]
    };
  }
}

customElements.define('nfc-reminder-card', NFCReminderCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'nfc-reminder-card',
  name: 'NFC Reminder Card',
  description: 'Track reminders with NFC tags'
});