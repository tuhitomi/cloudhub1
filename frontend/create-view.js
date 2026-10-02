import {appendCostSummary} from './product-view.js';
import {htmlText} from './i18n.js';
import {t as tr} from './i18n.js';
import {languageState,money} from './i18n.js';
import {templateText,profileLabel,profileDescription,regionLabel} from './catalog-text.js';
/**
 * CloudHub Creation View Component (Vanilla ES Module)
 * Conforms to CONTRACT.md & TASK.md
 *
 * 4 Steps:
 *  Step 0: Cấu hình (Configuration & Forecast Hours)
 *  Step 1: Chế độ vận hành (Operating mode & Lifecycle)
 *  Step 2: Dự toán chi phí (Cost estimates, Assumptions & Disclaimers)
 *  Step 3: Xác nhận tạo (Final review, Consent & Safe Retry Submit)
 */

/**
 * Creates and mounts the CloudHub environment creation view.
 *
 * @param {Object} callbacks
 * @param {Function} callbacks.onFieldChange - Callback with patch object { fieldName: stringValue }
 * @param {Function} callbacks.onNext - Callback when advancing step
 * @param {Function} callbacks.onBack - Callback when stepping back
 * @param {Function} callbacks.onConsent - Callback when user toggles consent checkbox (boolean)
 * @param {Function} callbacks.onRetryQuote - Callback when user retries quote fetch
 * @param {Function} callbacks.onCancel - Callback when user cancels
 * @param {Function} callbacks.onSubmit - Callback when form is submitted
 * @returns {{ update: (props: Object) => void }}
 */
export function createCreationView(callbacks = {}) {
  const dialog = document.querySelector('#create-dialog');
  if (!dialog) {
    return {
      update() {}
    };
  }

  // Ensure accessible dialog title linkage
  dialog.setAttribute('aria-labelledby', 'create-title');

  // Static functional presentation markup injected ONCE
  dialog.innerHTML = `
    <form id="create-form" novalidate>
      <div class="create-header">
        <h2 id="create-title">${htmlText("ui.f461ab2d8dc0")}</h2>
        <div id="create-notice" class="create-notice" role="status" aria-live="polite" hidden></div>
      </div>

      <nav class="create-stepper" aria-label="${htmlText("ui.f01926428d70")}">
        <ol class="step-indicator">
          <li id="step-nav-0" class="step-item is-active" aria-current="step">
            <span class="step-num">1</span>
            <span class="step-text">${htmlText("ui.f30b26e523e0")}</span>
          </li>
          <li id="step-nav-1" class="step-item">
            <span class="step-num">2</span>
            <span class="step-text">${htmlText("ui.c30af32de8c5")}</span>
          </li>
          <li id="step-nav-2" class="step-item">
            <span class="step-num">3</span>
            <span class="step-text">${htmlText("ui.1fe1186079e1")}</span>
          </li>
          <li id="step-nav-3" class="step-item">
            <span class="step-num">4</span>
            <span class="step-text">${htmlText("ui.1503b0d05f3d")}</span>
          </li>
        </ol>
      </nav>

      <h3 id="create-step-title" class="create-step-title">${htmlText("ui.76a25c0b2cd3")}</h3>
      <p id="create-quote-validity" class="info-banner" hidden></p>
      <p id="create-quote-notice" class="info-banner" role="status" hidden></p>

      <!-- Bước 0: Cấu hình -->
      <fieldset id="step-fieldset-0" class="step-fieldset">
        <legend class="sr-only">${htmlText("ui.eb41b2d6fb8c")}</legend>
        <div class="card-callout">
          <p id="configuration-description" class="field-desc"></p>
          <div id="template-meta" class="template-meta-pills"></div>
        </div>
        <button id="create-assess" type="button" class="btn btn-secondary">${htmlText('rec.assessButton')}</button>
        <p id="create-workload-note" class="info-banner" hidden>${htmlText('rec.planningAttached')}</p>
        <p id="create-limits" class="info-banner" role="status"></p>

        <div id="deployment-region-field" class="form-group">
          <label for="deployment-region">${htmlText("ui.aa7a3573a21d")}</label>
          <select id="deployment-region"></select>
          <small id="deployment-region-hint" class="field-hint"></small>
          <span id="deployment-region-error" class="field-error" role="alert" hidden></span>
        </div>

        <div class="form-group">
          <label for="configuration-variant">${htmlText("ui.572944f070ec")}</label>
          <select id="configuration-variant">
            <option value="standard" selected>${htmlText("ui.67f6dc83c0d4")}</option>
          </select>
          <small id="configuration-hint" class="field-hint"></small>
          <span id="configuration-error" class="field-error" role="alert" hidden></span>
        </div>

        <div class="form-group">
          <label for="hours">${htmlText("ui.1ad3b95c991e")}</label>
          <select id="hours">
            <option value="1">${htmlText("ui.d06edd9a88f1")}</option>
            <option value="2">${htmlText("ui.081d2a061e6a")}</option>
            <option value="4">${htmlText("ui.b9d441fcd3f6")}</option>
            <option value="8">${htmlText("ui.1f522cde5fc6")}</option>
          </select>
          <span id="hours-error" class="field-error" role="alert" hidden></span>
          <small class="field-hint">${htmlText("ui.e12632dbf624")}</small>
        </div>
        <section id="application-fields" hidden>
          <h3 data-i18n="ux.app.heading"></h3>
          <label for="application-release" data-i18n="ux.app.version"></label><select id="application-release"></select>
          <p id="application-hint" role="status"></p><p id="application-release-error" class="field-error" role="alert"></p>
          <label for="application-title" data-i18n="ux.app.title"></label><input id="application-title" maxlength="80">
          <p id="application-title-error" class="field-error" role="alert"></p>
          <label for="application-subtitle" data-i18n="ux.app.subtitle"></label><input id="application-subtitle" maxlength="240">
        </section>
      </fieldset>

      <!-- Bước 1: Chế độ vận hành -->
      <fieldset id="step-fieldset-1" class="step-fieldset" hidden disabled>
        <legend class="sr-only">${htmlText("ui.f11383e789df")}</legend>
        <div class="form-group">
          <label for="operating-mode">${htmlText("ui.3faa4d9b8739")}</label>
          <select id="operating-mode">
            <option value="AUTO_OFF">${htmlText("ui.cb445c400428")}</option>
            <option value="AUTO_RENEW">${htmlText("ui.0b686847e426")}</option>
          </select>
          <span id="operating-mode-error" class="field-error" role="alert" hidden></span>
          <p id="operating-explanation" class="field-desc"></p>
        </div>

        <div class="form-group">
          <label for="operating-period" id="operating-period-label">${htmlText("ui.dee26053f74c")}</label>
          <select id="operating-period">
            <option value="5">${htmlText("ui.e98d21d5aef5")}</option>
            <option value="15">${htmlText("ui.43786c01e7ed")}</option>
            <option value="60">${htmlText("ui.d06edd9a88f1")}</option>
            <option value="240">${htmlText("ui.b9d441fcd3f6")}</option>
            <option value="480">${htmlText("ui.1f522cde5fc6")}</option>
          </select>
          <div id="period-shortcuts" class="choice-chips" role="group" aria-labelledby="operating-period-label"></div>
          <span id="operating-period-error" class="field-error" role="alert" hidden></span>
          <small class="field-hint">${htmlText("ui.de8dedf8a72f")}</small>
        </div>

        <div class="form-group">
          <label id="operating-budget-field" for="operating-budget" hidden>
            ${htmlText("ui.2b8901f323f8")}
            <input id="operating-budget" type="number" min="0.001" step="0.001" placeholder="10.000">
          </label>
          <span id="operating-budget-error" class="field-error" role="alert" hidden></span>
          <small id="operating-budget-hint" class="field-hint" hidden>${htmlText("ui.0dfd3d9afc26")}</small>
        </div>

        <div class="form-group">
          <label for="ending-policy">${htmlText("ui.b6cba46cd1d8")}</label>
          <select id="ending-policy">
            <option value="BACKUP_RETIRE">${htmlText("ui.7a55a8bbb069")}</option>
            <option value="PAUSE">${htmlText("ui.c8cf16e25acf")}</option>
          </select>
          <span id="ending-policy-error" class="field-error" role="alert" hidden></span>
          <p id="pause-support" class="field-desc"></p>
          <p id="backup-description" class="field-desc"></p>
        </div>
      </fieldset>

      <!-- Bước 2: Dự toán -->
      <fieldset id="step-fieldset-2" class="step-fieldset" hidden disabled>
        <legend class="sr-only">${htmlText("ui.a7c22b451daf")}</legend>
        <div id="quote" class="quote-container" aria-live="polite"></div>
      </fieldset>

      <!-- Bước 3: Xác nhận -->
      <fieldset id="step-fieldset-3" class="step-fieldset" hidden disabled>
        <legend class="sr-only">${htmlText("ui.e7b8de5aeed8")}</legend>
        <div id="review-summary" class="review-summary-container"></div>

        <div class="consent-group">
          <label class="checkbox-label" for="confirm-cost">
            <input id="confirm-cost" type="checkbox" required>
            <span>${htmlText("ui.47a0f2b0a310")}</span>
          </label>
        </div>
      </fieldset>

      <div class="actions create-actions">
        <button type="button" id="cancel">${htmlText("ui.74fcd3522be7")}</button>
        <button type="button" id="create-back" hidden>${htmlText("ui.6d7935822966")}</button>
        <button type="button" id="create-next">${htmlText("ui.87a7ae881fae")}</button>
        <button type="submit" id="confirm" disabled hidden>${htmlText("ui.fbb8938773fa")}</button>
      </div>
    </form>
  `;

  // Query DOM elements once
  const form = dialog.querySelector('#create-form');
  const createTitleEl = dialog.querySelector('#create-title');
  const createStepTitleEl = dialog.querySelector('#create-step-title');
  const createNoticeEl = dialog.querySelector('#create-notice');

  const stepNavItems = [
    dialog.querySelector('#step-nav-0'),
    dialog.querySelector('#step-nav-1'),
    dialog.querySelector('#step-nav-2'),
    dialog.querySelector('#step-nav-3')
  ];

  const fieldsets = [
    dialog.querySelector('#step-fieldset-0'),
    dialog.querySelector('#step-fieldset-1'),
    dialog.querySelector('#step-fieldset-2'),
    dialog.querySelector('#step-fieldset-3')
  ];

  // Step 0 elements
  const configDescEl = dialog.querySelector('#configuration-description');
  const templateMetaEl = dialog.querySelector('#template-meta');
  const createLimitsEl = dialog.querySelector('#create-limits');
  dialog.querySelector('#create-assess').onclick=()=>callbacks.onAssess?.();
  const configVariantSelect = dialog.querySelector('#configuration-variant');
  const regionSelect=dialog.querySelector('#deployment-region');
  regionSelect.addEventListener('change',()=>callbacks.onFieldChange?.({region:regionSelect.value}));
  const hoursSelect = dialog.querySelector('#hours');
  const hoursError = dialog.querySelector('#hours-error');

  // Step 1 elements
  const operatingModeSelect = dialog.querySelector('#operating-mode');
  const operatingModeError = dialog.querySelector('#operating-mode-error');
  const operatingExplanationEl = dialog.querySelector('#operating-explanation');
  const operatingPeriodSelect = dialog.querySelector('#operating-period');
  const operatingPeriodError = dialog.querySelector('#operating-period-error');
  const operatingBudgetField = dialog.querySelector('#operating-budget-field');
  const operatingBudgetInput = dialog.querySelector('#operating-budget');
  const operatingBudgetError = dialog.querySelector('#operating-budget-error');
  const operatingBudgetHint = dialog.querySelector('#operating-budget-hint');
  const endingPolicySelect = dialog.querySelector('#ending-policy');
  const endingPolicyError = dialog.querySelector('#ending-policy-error');
  const pauseSupportEl = dialog.querySelector('#pause-support');
  const backupDescriptionEl = dialog.querySelector('#backup-description');

  // Step 2 elements
  const quoteEl = dialog.querySelector('#quote');

  // Step 3 elements
  const reviewSummaryEl = dialog.querySelector('#review-summary');
  const confirmCostCheckbox = dialog.querySelector('#confirm-cost');

  // Action buttons
  const cancelBtn = dialog.querySelector('#cancel');
  const createBackBtn = dialog.querySelector('#create-back');
  const createNextBtn = dialog.querySelector('#create-next');
  const confirmBtn = dialog.querySelector('#confirm');

  // State cache for avoiding unnecessary updates and keeping focus/caret
  let lastState = {
    step: 0,
    canSubmit: false,
    busy: false,
    uncertain: false
  };

  // Helper to update textContent only if different
  function setTextIfChanged(element, text) {
    if (!element) return;
    const next = text == null ? '' : String(text);
    if (element.textContent !== next) {
      element.textContent = next;
    }
  }

  // Bind event listeners ONCE
  for(const [id,key] of [['application-release','appRelease'],['application-title','appTitle'],['application-subtitle','appSubtitle']])dialog.querySelector('#'+id).addEventListener(id==='application-release'?'change':'input',event=>callbacks.onFieldChange?.({[key]:event.target.value}));
  configVariantSelect.addEventListener('change',()=>callbacks.onFieldChange?.({configurationId:configVariantSelect.value}));
  hoursSelect.addEventListener('change', () => {
    callbacks.onFieldChange?.({ estimateHours: hoursSelect.value });
  });

  operatingModeSelect.addEventListener('change', () => {
    callbacks.onFieldChange?.({ mode: operatingModeSelect.value });
  });

  operatingPeriodSelect.addEventListener('change', () => {
    callbacks.onFieldChange?.({ periodMinutes: operatingPeriodSelect.value });
  });
  const shortcuts=dialog.querySelector('#period-shortcuts');
  const periodKeys={'5':'ui.e98d21d5aef5','15':'ui.43786c01e7ed','60':'ui.d06edd9a88f1','240':'ui.b9d441fcd3f6','480':'ui.1f522cde5fc6'};
  for(const value of Object.keys(periodKeys)){
    const button=document.createElement('button');button.type='button';button.dataset.minutes=value;button.textContent=tr(periodKeys[value]);
    button.addEventListener('click',()=>callbacks.onFieldChange?.({periodMinutes:value}));shortcuts.append(button);
  }

  endingPolicySelect.addEventListener('change', () => {
    callbacks.onFieldChange?.({ endingPolicy: endingPolicySelect.value });
  });

  operatingBudgetInput.addEventListener('input', () => {
    callbacks.onFieldChange?.({ budgetUsd: operatingBudgetInput.value });
  });

  operatingBudgetInput.addEventListener('change', () => {
    callbacks.onFieldChange?.({ budgetUsd: operatingBudgetInput.value });
  });

  confirmCostCheckbox.addEventListener('change', () => {
    callbacks.onConsent?.(Boolean(confirmCostCheckbox.checked));
  });

  createNextBtn.addEventListener('click', () => {
    callbacks.onNext?.();
  });

  createBackBtn.addEventListener('click', () => {
    callbacks.onBack?.();
  });

  cancelBtn.addEventListener('click', () => {
    callbacks.onCancel?.();
  });

  // Safe form submission:
  // When uncertain, canSubmit is true and allows resending the SAME request safely.
  // Only `busy` blocks submission!
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (lastState.step === 3 && lastState.canSubmit && !lastState.busy) {
      callbacks.onSubmit?.();
    }
  });

  /**
   * Main update function called by GPT lifecycle coordinator.
   *
   * @param {Object} props
   */
  function update(props = {}) {
    tick(props);
    dialog.querySelector('#create-workload-note').hidden=!props.planningWorkload;
    dialog.querySelector('#create-workload-note').textContent=tr('rec.planningAttached');
    dialog.querySelector('#create-assess').textContent=tr('rec.assessButton');
    dialog.querySelector('#create-assess').disabled=props.busy||props.uncertain;
    const step = typeof props.step === 'number' && props.step >= 0 && props.step <= 3 ? props.step : 0;
    const formVals = props.form || {};
    const errors = props.errors || {};
    const template = props.template || {};
    const busy = Boolean(props.busy);
    const uncertain = Boolean(props.uncertain);
    const canNext = Boolean(props.canNext);
    const canSubmit = Boolean(props.canSubmit);
    const canCancel = Boolean(props.canCancel);
    const supportsPause = Boolean(props.supportsPause);

    lastState = { step, canSubmit, busy, uncertain };

    // 1. Update Title and Step Title
    setTextIfChanged(createTitleEl, props.title || tr("ui.f461ab2d8dc0"));
    const stepNames = [
      tr("ui.76a25c0b2cd3"),
      tr("ui.e31206807774"),
      tr("ui.db422c7b2316"),
      tr("ui.86a4d2acc0a7")
    ];
    setTextIfChanged(createStepTitleEl, stepNames[step]);

    // 2. Update Stepper Nav indicators
    for (let i = 0; i < 4; i++) {
      const navItem = stepNavItems[i];
      if (!navItem) continue;
      navItem.classList.remove('is-active', 'is-complete', 'is-upcoming');
      if (i === step) {
        navItem.classList.add('is-active');
        navItem.setAttribute('aria-current', 'step');
      } else if (i < step) {
        navItem.classList.add('is-complete');
        navItem.removeAttribute('aria-current');
      } else {
        navItem.classList.add('is-upcoming');
        navItem.removeAttribute('aria-current');
      }
    }

    // 3. Update Fieldset Visibility & Disabled States
    // Inactive fieldsets must be disabled so browser validation doesn't block submission.
    // Uncertain requests freeze inputs, but the recovered review still needs
    // explicit consent to retry exactly the original command.
    for (let i = 0; i < 4; i++) {
      const fs = fieldsets[i];
      if (!fs) continue;
      const isActive = i === step;
      fs.hidden = !isActive;
      fs.disabled = !isActive || busy || (uncertain && i !== 3);
    }

    // 4. Update Notice & Global Error / Busy / Uncertain State
    if (busy) {
      createNoticeEl.hidden = false;
      createNoticeEl.className = 'create-notice is-busy';
      createNoticeEl.setAttribute('role', 'status');
      setTextIfChanged(createNoticeEl, tr("ui.8b96ca57d2f4"));
    } else if (uncertain) {
      createNoticeEl.hidden = false;
      createNoticeEl.className = 'create-notice is-uncertain';
      createNoticeEl.setAttribute('role', 'alert');
      setTextIfChanged(
        createNoticeEl,
        props.error || tr("ui.b0970472ebef")
      );
    } else if (props.error) {
      createNoticeEl.hidden = false;
      createNoticeEl.className = 'create-notice is-error';
      createNoticeEl.setAttribute('role', 'alert');
      setTextIfChanged(createNoticeEl, props.error);
    } else {
      createNoticeEl.hidden = true;
      createNoticeEl.className = 'create-notice';
      setTextIfChanged(createNoticeEl, '');
    }

    // 5. Update Step 0: Cấu hình & Khoảng xem dự toán
    const regions=template.regions||[];
    dialog.querySelector('#deployment-region-field').hidden=!regions.length;
    const regionKey=JSON.stringify([languageState().locale,regions.map(r=>[r.region,r.name,r.status])]);
    if(regionSelect.dataset.regionsKey!==regionKey){regionSelect.replaceChildren();for(const r of regions){const o=document.createElement('option');o.value=r.region;o.textContent=regionLabel(r)+' — '+r.region+' · '+({SUPPORTED:tr("ui.03dae63787ac"),VERIFYING:tr("ui.d92e9b9c0ba1"),UNAVAILABLE:tr("ui.150b16ddc9f4")}[r.status]||tr("ui.150b16ddc9f4"));regionSelect.append(o);}regionSelect.dataset.regionsKey=regionKey;}
    regionSelect.value=formVals.region||template.default_region||'';
    regionSelect.disabled=!!props.configurationLocked||busy||uncertain;
    setTextIfChanged(dialog.querySelector('#deployment-region-hint'),props.configurationLocked?tr("ui.217decaca6e5"):tr("ui.a42720811564"));
    updateInlineError(dialog.querySelector('#deployment-region-error'),regionSelect,errors.region);
    const appFields=dialog.querySelector('#application-fields');appFields.hidden=!['T03','T04'].includes(template.template_id);
    for(const label of appFields.querySelectorAll('[data-i18n]'))setTextIfChanged(label,tr(label.getAttribute('data-i18n')));
    const appOptions=(template.application_options?.[formVals.region]||[]).map(a=>({...a,enabled:a.enabled&&(!a.configuration_ids||a.configuration_ids.includes(formVals.configurationId||'standard'))})),appSelect=dialog.querySelector('#application-release');
    const appKey=JSON.stringify([languageState().locale,appOptions]);
    if(appSelect.dataset.optionsKey!==appKey){appSelect.replaceChildren();const legacy=document.createElement('option');legacy.value='';legacy.textContent=tr('ux.app.legacy');appSelect.append(legacy);for(const app of appOptions){const opt=document.createElement('option');opt.value=app.release_id;opt.textContent=app.release_id+(app.enabled?'':' · '+tr('ux.app.pending'));opt.disabled=!app.enabled;appSelect.append(opt);}appSelect.dataset.optionsKey=appKey;}
    appSelect.value=formVals.appRelease||'';appSelect.disabled=!!props.configurationLocked||busy||uncertain;
    for(const [id,key] of [['application-title','appTitle'],['application-subtitle','appSubtitle']]){const input=dialog.querySelector('#'+id);if(input.value!==(formVals[key]||''))input.value=formVals[key]||'';input.disabled=!formVals.appRelease||!!props.configurationLocked||busy||uncertain;}
    setTextIfChanged(dialog.querySelector('#application-hint'),appOptions.some(a=>a.enabled)?tr('ux.app.scope'):tr('ux.app.pending'));
    for(const [id,key] of [['application-release-error','appRelease'],['application-title-error','appTitle']])setTextIfChanged(dialog.querySelector('#'+id),errors[key]||'');
    const profiles=template.configuration_options||[{id:'standard',label:tr("ui.67f6dc83c0d4"),description:props.description,create_enabled:true}];
    const profilesKey=JSON.stringify([languageState().locale,profiles.map(p=>[p.id,p.label,p.create_enabled])]);
    if(configVariantSelect.dataset.profilesKey!==profilesKey){configVariantSelect.replaceChildren();for(const p of profiles){const o=document.createElement('option');o.value=p.id;o.textContent=profileLabel(template,p)+(p.create_enabled===false?tr("ui.7768e1a4bb1a"):'');configVariantSelect.append(o);}configVariantSelect.dataset.profilesKey=profilesKey;}
    configVariantSelect.value=formVals.configurationId||'standard';
    configVariantSelect.disabled=!!props.configurationLocked||busy||uncertain;
    const selectedProfile=profiles.find(p=>p.id===(formVals.configurationId||'standard'));
    setTextIfChanged(dialog.querySelector('#configuration-hint'),props.configurationLocked?tr("ui.50b430c59ec4"):selectedProfile?.create_enabled===false?tr("ui.60904d2b924b"):tr("ui.8692147f78e9"));
    updateInlineError(dialog.querySelector('#configuration-error'),configVariantSelect,errors.configurationId);
    const descText =
      selectedProfile?.configuration ? profileDescription(template,selectedProfile) : props.description ||
      template.purpose ||
      template.configuration ||
      tr("ui.5d6b9f01af6b");
    setTextIfChanged(configDescEl, descText);

    // Render template meta pills cleanly without [object Object]
    if (templateMetaEl) {
      templateMetaEl.replaceChildren();
      if (template.name) {
        const span = document.createElement('span');
        span.className = 'badge badge-primary';
        span.textContent = templateText(template);
        templateMetaEl.appendChild(span);
      }
      if (template.template_id) {
        const span = document.createElement('span');
        span.className = 'badge';
        span.textContent = tr("ui.54b9a5f2eb93",{p0:(template.template_id)});
        templateMetaEl.appendChild(span);
      }
      // Readable badge for pause capability
      const pauseBadge = document.createElement('span');
      pauseBadge.className = supportsPause ? 'badge badge-success' : 'badge badge-info';
      pauseBadge.textContent = supportsPause ? tr("ui.1a6123432da6") : tr("ui.193377b6929c");
      templateMetaEl.appendChild(pauseBadge);
    }

    const limitsText = props.limitsText || tr("ui.3c6ade442f0b");
    setTextIfChanged(createLimitsEl, limitsText);

    if (formVals.estimateHours && hoursSelect.value !== String(formVals.estimateHours)) {
      hoursSelect.value = String(formVals.estimateHours);
    }
    updateInlineError(hoursError, hoursSelect, errors.estimateHours);

    // 6. Update Step 1: Chế độ vận hành
    if (formVals.mode && operatingModeSelect.value !== formVals.mode) {
      operatingModeSelect.value = formVals.mode;
    }
    const availableModes=template.operating_capabilities?.modes||['AUTO_OFF','AUTO_RENEW'];
    let continuous=operatingModeSelect.querySelector('[value=CONTINUOUS]');
    if(availableModes.includes('CONTINUOUS')&&!continuous){continuous=document.createElement('option');continuous.value='CONTINUOUS';continuous.textContent=tr('continuous.name');operatingModeSelect.append(continuous);}
    if(!availableModes.includes('CONTINUOUS')&&continuous)continuous.remove();
    operatingModeSelect.value=formVals.mode||'AUTO_OFF';
    operatingPeriodSelect.disabled=formVals.mode==='CONTINUOUS';
    for(const button of shortcuts.children){button.textContent=tr(periodKeys[button.dataset.minutes]);button.setAttribute('aria-pressed',String(button.dataset.minutes===String(formVals.periodMinutes)));button.disabled=formVals.mode==='CONTINUOUS'||!!props.busy||!!props.uncertain;}
    const isAutoRenew = formVals.mode === 'AUTO_RENEW';
    operatingBudgetField.hidden = !isAutoRenew&&formVals.mode!=='CONTINUOUS';
    if (operatingBudgetHint) {
      operatingBudgetHint.hidden = !isAutoRenew&&formVals.mode!=='CONTINUOUS';
    }

    // Operational mode explanation:
    // Renewal decision is based on committed estimate + next cycle vs cumulative budget cap, NOT actual incurred costs.
    if(formVals.mode==='CONTINUOUS'){setTextIfChanged(operatingExplanationEl,tr('continuous.explanation'));}
    else if (isAutoRenew) {
      setTextIfChanged(
        operatingExplanationEl,
        tr("ui.a8d444fb7e2b")
      );
    } else {
      setTextIfChanged(
        operatingExplanationEl,
        tr("ui.1421874f0373")
      );
    }

    if (formVals.periodMinutes && operatingPeriodSelect.value !== String(formVals.periodMinutes)) {
      operatingPeriodSelect.value = String(formVals.periodMinutes);
    }

    // Only update budget input value if user is not actively typing to protect caret position
    if (document.activeElement !== operatingBudgetInput) {
      const budgetVal = formVals.budgetUsd != null ? String(formVals.budgetUsd) : '';
      if (operatingBudgetInput.value !== budgetVal) {
        operatingBudgetInput.value = budgetVal;
      }
    }

    // Ending policy options based on supportsPause
    let pauseOption = endingPolicySelect.querySelector('option[value="PAUSE"]');
    if (!pauseOption) {
      pauseOption = document.createElement('option');
      pauseOption.value = 'PAUSE';
      pauseOption.textContent = tr("ui.c8cf16e25acf");
      endingPolicySelect.appendChild(pauseOption);
    }
    pauseOption.disabled = !supportsPause;
    pauseOption.hidden = !supportsPause;

    if (formVals.endingPolicy) {
      endingPolicySelect.value = formVals.endingPolicy;
    } else if (!supportsPause && endingPolicySelect.value === 'PAUSE') {
      endingPolicySelect.value = 'BACKUP_RETIRE';
    }

    // Clarify PAUSE vs BACKUP_RETIRE
    if (supportsPause) {
      setTextIfChanged(
        pauseSupportEl,
        tr("ui.6b6c22b91e17")
      );
      pauseSupportEl.className = 'field-desc field-desc-info';
    } else {
      setTextIfChanged(
        pauseSupportEl,
        tr("ui.8fe7ce4eb025")
      );
      pauseSupportEl.className = 'field-desc field-desc-muted';
    }

    const scopeStr = props.backupScope ? tr("ui.f4d04b56b97f",{p0:(props.backupScope)}) : tr("ui.4c8c77fe134b");
    setTextIfChanged(
      backupDescriptionEl,
      tr("ui.607db5f06899",{p0:(scopeStr)})
    );

    // Inline errors for Step 1
    updateInlineError(operatingModeError, operatingModeSelect, errors.mode);
    updateInlineError(operatingPeriodError, operatingPeriodSelect, errors.periodMinutes);
    updateInlineError(operatingBudgetError, operatingBudgetInput, errors.budgetUsd);
    updateInlineError(endingPolicyError, endingPolicySelect, errors.endingPolicy);

    // 7. Update Step 2: Dự toán
    renderQuoteView(quoteEl, props, callbacks);

    // 8. Update Step 3: Xác nhận & Kiểm tra
    renderReviewSummary(reviewSummaryEl, props);
    confirmCostCheckbox.checked = Boolean(props.consent);
    confirmCostCheckbox.disabled = busy || (!uncertain && props.quoteStatus!=='ready');

    // 9. Update Navigation Buttons
    cancelBtn.disabled = !canCancel;
    createBackBtn.hidden = step === 0;
    createBackBtn.disabled = busy || uncertain;

    createNextBtn.hidden = step === 3;
    createNextBtn.disabled = !canNext || busy || uncertain;

    confirmBtn.hidden = step !== 3;
    // CRITICAL: uncertain does NOT block submission when canSubmit=true; only busy blocks!
    confirmBtn.disabled = !canSubmit || busy;
    confirmBtn.textContent = uncertain ? tr("ui.9578987e8ea3") : tr("ui.fbb8938773fa");
  }

  function tick(props={}){
    const clock=dialog.querySelector('#create-quote-validity'),note=dialog.querySelector('#create-quote-notice');
    clock.hidden=!props.open||props.step<2||!props.quote||props.uncertain;
    clock.textContent=clock.hidden?'':tr('experience.quoteValidity',{seconds:props.quoteRemainingSeconds??0})+' '+tr('experience.quoteRule');
    note.hidden=!props.quoteNotice;note.textContent=props.quoteNotice||'';
  }
  return { update,tick };
}

/**
 * Updates inline error element and accessibility attributes on input.
 */
function updateInlineError(errorEl, inputEl, errorText) {
  if (!errorEl || !inputEl) return;
  if (errorText) {
    errorEl.hidden = false;
    if (errorEl.textContent !== errorText) {
      errorEl.textContent = errorText;
    }
    inputEl.setAttribute('aria-invalid', 'true');
    inputEl.setAttribute('aria-describedby', errorEl.id);
  } else {
    errorEl.hidden = true;
    if (errorEl.textContent !== '') {
      errorEl.textContent = '';
    }
    inputEl.removeAttribute('aria-invalid');
    if (inputEl.getAttribute('aria-describedby') === errorEl.id) {
      inputEl.removeAttribute('aria-describedby');
    }
  }
}

/**
 * Renders the Quote container based on quoteStatus.
 * Displays prominent disclaimer that quote does not guarantee cloud provider invoices right with the price.
 */
function renderQuoteView(container, props, callbacks) {
  if (!container) return;
  const quoteStatus = props.quoteStatus || 'idle';
  const busy = Boolean(props.busy);

  // Clear previous contents to prevent flashing old prices
  container.replaceChildren();

  if (quoteStatus === 'loading') {
    const loadingCard = document.createElement('div');
    loadingCard.className = 'quote-status-box quote-loading';
    loadingCard.setAttribute('role', 'status');

    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    spinner.setAttribute('aria-hidden', 'true');

    const msg = document.createElement('span');
    msg.textContent = tr("ui.181d0530080b");

    loadingCard.append(spinner, msg);
    container.appendChild(loadingCard);
    return;
  }

  if (quoteStatus === 'error') {
    const errorCard = document.createElement('div');
    errorCard.className = 'quote-status-box quote-error';
    errorCard.setAttribute('role', 'alert');

    const msg = document.createElement('p');
    msg.className = 'quote-error-text';
    msg.textContent = tr("ui.bdbc72b01d16");

    const retryBtn = document.createElement('button');
    retryBtn.type = 'button';
    retryBtn.id = 'create-retry-quote';
    retryBtn.className = 'btn btn-secondary btn-retry';
    retryBtn.textContent = tr("ui.0527afede54b");
    retryBtn.disabled = busy;
    retryBtn.addEventListener('click', () => {
      callbacks.onRetryQuote?.();
    });

    errorCard.append(msg, retryBtn);
    container.appendChild(errorCard);
    return;
  }

  if (quoteStatus === 'ready') {
    // Top Metadata Row
    const metaRow = document.createElement('div');
    metaRow.className = 'quote-meta-row';

    if (props.region) {
      const pill = document.createElement('span');
      pill.className = 'quote-pill';
      pill.textContent = tr("ui.8d0fcabe6c4f",{p0:(props.region)});
      metaRow.appendChild(pill);
    }
    if (props.priceUpdatedAt) {
      const pill = document.createElement('span');
      pill.className = 'quote-pill';
      pill.textContent = tr("ui.e5ecbcbcf6e4",{p0:(props.priceUpdatedAt)});
      metaRow.appendChild(pill);
    }
    if (props.budgetScope) {
      const pill = document.createElement('span');
      pill.className = 'quote-pill';
      pill.textContent = tr("ui.c61deb82504e",{p0:(props.budgetScope)});
      metaRow.appendChild(pill);
    }

    if (metaRow.children.length > 0) {
      container.appendChild(metaRow);
    }

    // Prominent invoice disclaimer displayed right with the price
    const disclaimerBanner = document.createElement('div');
    disclaimerBanner.className = 'quote-disclaimer-banner';
    disclaimerBanner.setAttribute('role', 'note');
    disclaimerBanner.textContent =
      tr("ui.5940f727d99c");
    container.appendChild(disclaimerBanner);

    // Quote Rows (provided and formatted by GPT)
    if (Array.isArray(props.quoteRows) && props.quoteRows.length > 0) {
      const table = document.createElement('div');
      table.className = 'quote-rows-table';

      for (const row of props.quoteRows) {
        const item = document.createElement('div');
        item.className = 'quote-row-item';

        const label = document.createElement('span');
        label.className = 'quote-row-label';
        label.textContent = row.label || '';

        const val = document.createElement('strong');
        val.className = 'quote-row-value';
        val.textContent = row.value || '';

        item.append(label, val);
        table.appendChild(item);
      }
      container.appendChild(table);
    }

    // Collapsible Details: Assumptions, Unknowns, Raw breakdown
    const details = document.createElement('details');
    details.className = 'quote-assumptions-disclosure';

    const summary = document.createElement('summary');
    summary.textContent = tr("ui.a318a12d348e");
    details.appendChild(summary);

    const detailsBody = document.createElement('div');
    detailsBody.className = 'quote-details-body';

    for(const key of ['first','renewal','after_shutdown'])if(props.assumptions?.[key]){
      const section=document.createElement('section'),title=document.createElement('h4');
      title.textContent=tr('ux.period.'+key);section.append(title);appendCostSummary(section,props.assumptions[key]);detailsBody.append(section);
    }
    const technical=document.createElement('details'),technicalTitle=document.createElement('summary'),raw=document.createElement('pre');
    technicalTitle.textContent=tr('rec.technical');raw.textContent=JSON.stringify({quote:props.quote,assumptions:props.assumptions},null,2);technical.append(technicalTitle,raw);detailsBody.append(technical);

    // Unknown variables
    if (Array.isArray(props.unknown) && props.unknown.length > 0) {
      const unkSection = document.createElement('div');
      unkSection.className = 'quote-detail-section';

      const h4 = document.createElement('h4');
      h4.textContent = tr("ui.7e2deb28d652");
      unkSection.appendChild(h4);

      const ul = document.createElement('ul');
      ul.className = 'unknown-list';
      for (const u of props.unknown) {
        const li = document.createElement('li');
        li.textContent = String(u);
        ul.appendChild(li);
      }
      unkSection.appendChild(ul);
      detailsBody.appendChild(unkSection);
    }

    details.appendChild(detailsBody);
    container.appendChild(details);
    return;
  }

  // Idle fallback
  const idleCard = document.createElement('div');
  idleCard.className = 'quote-status-box quote-idle';
  const p = document.createElement('p');
  p.textContent = tr("ui.58dba7b9b1df");
  idleCard.appendChild(p);
  container.appendChild(idleCard);
}

/**
 * Renders the Step 3 Final Review Summary before confirmation.
 */
function renderReviewSummary(container, props) {
  if (!container) return;
  const formVals = props.form || {};
  const template = props.template || {};

  container.replaceChildren();

  const card = document.createElement('div');
  card.className = 'summary-review-card';

  const h4 = document.createElement('h4');
  h4.className = 'summary-title';
  h4.textContent = tr("ui.fe40690868d1");
  card.appendChild(h4);

  const grid = document.createElement('div');
  grid.className = 'summary-grid';

  const items = [
    { label: tr("ui.7f2a1283bf8f"), value: templateText(template) || props.title || tr("ui.7023a44f1ce8") },
    { label: tr("ui.572944f070ec"), value: profileLabel(template,template.configuration_options?.find(p=>p.id===(formVals.configurationId||'standard')))||tr("ui.67f6dc83c0d4") },
    ...(formVals.region?[{label:tr("ui.aa7a3573a21d"),value:formVals.region}]:[]),
    ...(formVals.appRelease?[{label:tr('ux.app.version'),value:formVals.appRelease},{label:tr('ux.app.title'),value:formVals.appTitle||''},...(formVals.appSubtitle?[{label:tr('ux.app.subtitle'),value:formVals.appSubtitle}]:[])]:[]),
    {
      label: tr("ui.f7fc0d172ba2"),
      value: tr("ui.5d1d4d8adfe3",{p0:(formVals.estimateHours || '1')})
    },
    {
      label: tr("ui.3faa4d9b8739"),
      value: formVals.mode==='CONTINUOUS'?tr('continuous.name'):formVals.mode === 'AUTO_RENEW' ? tr("ui.0b686847e426") : tr("ui.cb445c400428")
    },
    {
      label: tr("ui.f3cc55f68188"),
      value: formVals.mode==='CONTINUOUS'?tr('continuous.noDeadline'):tr("ui.e711148f419a",{p0:(formVals.periodMinutes || '60')})
    },
    {
      label: tr("ui.72c1d4a1f39f"),
      value: formVals.mode==='CONTINUOUS'?tr('continuous.name'):formVals.mode === 'AUTO_RENEW' ? money(Number(formVals.budgetUsd||10)*1000) : tr("ui.422a89f99587")
    },
    {
      label: tr("ui.6083cf70f9ad"),
      value: formVals.endingPolicy === 'PAUSE' ? tr("ui.c8cf16e25acf") : tr("ui.7a55a8bbb069")
    }
  ];

  for (const item of items) {
    const row = document.createElement('div');
    row.className = 'summary-item';

    const lbl = document.createElement('span');
    lbl.className = 'summary-label';
    lbl.textContent = item.label;

    const val = document.createElement('strong');
    val.className = 'summary-value';
    val.textContent = item.value;

    row.append(lbl, val);
    grid.appendChild(row);
  }
  card.appendChild(grid);

  // Cost summary preview if quoteRows exists
  if (Array.isArray(props.quoteRows) && props.quoteRows.length > 0) {
    const costBox = document.createElement('div');
    costBox.className = 'summary-cost-preview';

    const costTitle = document.createElement('span');
    costTitle.className = 'summary-cost-title';
    costTitle.textContent = tr("ui.927b47e63235");

    const costList = document.createElement('span');
    costList.className = 'summary-cost-values';
    costList.textContent = props.quoteRows.map((r) => `${r.label}: ${r.value}`).join(' • ');

    costBox.append(costTitle, costList);
    card.appendChild(costBox);
  }

  // Clear distinction between PAUSE and BACKUP_RETIRE
  const noticeBox = document.createElement('div');
  noticeBox.className = 'summary-retention-notice';
  const scopeStr = props.backupScope ? tr("ui.f4d04b56b97f",{p0:(props.backupScope)}) : tr("ui.4c8c77fe134b");

  if (formVals.endingPolicy === 'PAUSE') {
    noticeBox.textContent =
      tr("ui.70d4bf4bae91");
  } else {
    noticeBox.textContent =
      tr("ui.becbdc5d38d3",{p0:(scopeStr)});
  }
  card.appendChild(noticeBox);

  container.appendChild(card);
}
