function toggleMenu(){document.getElementById('sidebar').classList.toggle('open')}

/* ---------- Dropdown de notificações ---------- */
function toggleNotifications(event){
	event.stopPropagation();
	const dropdown=document.getElementById('notifDropdown');
	if(dropdown) dropdown.classList.toggle('show');
}
document.addEventListener('click',function(event){
	const dropdown=document.getElementById('notifDropdown');
	if(dropdown && !event.target.closest('.notif-wrap')) dropdown.classList.remove('show');
});
document.addEventListener('keydown',function(event){
	if(event.key==='Escape'){
		const dropdown=document.getElementById('notifDropdown');
		if(dropdown) dropdown.classList.remove('show');
	}
});


/* ---------- Campos de pesquisa para hóspedes e quartos/unidades ---------- */
function setupSearchableSelects(){
	const selectors = 'select[name="guest_id"], select[name="room_id"]:not(#guestRoomSelect):not(#paymentRoom), select[name="clean_room"], select[name="maint_room"], select[id="cleaning_room"], select[id="maintenance_room"]';
	document.querySelectorAll(selectors).forEach(function(select){
		if (select.dataset.searchableReady === 'true' || select.closest('.searchable-select')) return;
		select.dataset.searchableReady = 'true';

		const wrapper = document.createElement('div');
		wrapper.className = 'searchable-select';
		select.parentNode.insertBefore(wrapper, select);
		wrapper.appendChild(select);
		select.classList.add('searchable-select-native');

		const isGuest = select.name === 'guest_id';
		const isRequired = select.required;
		const placeholder = isGuest ? 'Pesquisar hóspede por nome...' : 'Pesquisar quarto ou unidade...';
		const search = document.createElement('input');
		search.type = 'search';
		search.className = 'searchable-select-input';
		search.placeholder = placeholder;
		search.autocomplete = 'off';
		search.setAttribute('aria-label', placeholder);
		if (isRequired) search.required = true;

		const results = document.createElement('div');
		results.className = 'searchable-select-results';
		results.hidden = true;
		wrapper.appendChild(search);
		wrapper.appendChild(results);

		const options = Array.from(select.options).map(function(option){
			return {value: option.value, text: option.textContent.trim(), disabled: option.disabled};
		});
		const selected = select.options[select.selectedIndex];
		if (selected && selected.value) search.value = selected.textContent.trim();

		function closeResults(){ results.hidden = true; }
		function choose(option){
			select.value = option.value;
			search.value = option.value ? option.text : '';
			search.setCustomValidity('');
			closeResults();
			select.dispatchEvent(new Event('change', {bubbles:true}));
		}
		function renderResults(){
			const term = search.value.trim().toLocaleLowerCase('pt-BR');
			results.innerHTML = '';
			options.filter(function(option){
				return !option.disabled && option.text.toLocaleLowerCase('pt-BR').includes(term);
			}).slice(0, 40).forEach(function(option){
				const button = document.createElement('button');
				button.type = 'button';
				button.className = 'searchable-select-option';
				button.textContent = option.text;
				button.addEventListener('click', function(){ choose(option); });
				results.appendChild(button);
			});
			results.hidden = results.children.length === 0;
		}

		search.addEventListener('focus', renderResults);
		search.addEventListener('input', function(){
			select.value = '';
			if (isRequired) search.setCustomValidity('Selecione uma opção da pesquisa.');
			renderResults();
		});
		search.addEventListener('keydown', function(event){
			if (event.key === 'Escape') closeResults();
		});
		select.addEventListener('change', function(){
			const current = select.options[select.selectedIndex];
			if (current && current.value) search.value = current.textContent.trim();
		});
		search.addEventListener('blur', function(){
			setTimeout(closeResults, 150);
		});
	});
}

document.addEventListener('DOMContentLoaded', function(){
	setupSearchableSelects();
	document.querySelectorAll('.flash').forEach(function(message){
		const closeButton = document.createElement('button');
		closeButton.type = 'button';
		closeButton.className = 'flash-close';
		closeButton.setAttribute('aria-label', 'Fechar mensagem');
		closeButton.textContent = '×';
		closeButton.addEventListener('click', function(){ message.remove(); });
		message.appendChild(closeButton);
	});

	document.querySelectorAll('form.professional-filter:not(#roomsFilters), form.operation-filters').forEach(function(form){
		const submit = function(){ form.submit(); };
		let timer = null;

		form.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), select').forEach(function(field){
			if (field.classList.contains('searchable-select-input')) return;
			if (field.hasAttribute('data-no-autosubmit')) return;
			if (field.tagName === 'SELECT') {
				field.addEventListener('change', submit);
				return;
			}

			field.addEventListener('input', function(){
				clearTimeout(timer);
				timer = setTimeout(submit, 180);
			});
			field.addEventListener('keydown', function(event){
				if (event.key === 'Enter') event.preventDefault();
			});
		});

		form.querySelectorAll('button').forEach(function(button){
			button.hidden = true;
		});
	});

	/* ---------- Filtro de período (dia/semana/mês/ano) ---------- */
	function isoWeekString(d){
		const date = new Date(d.getTime());
		date.setHours(0,0,0,0);
		date.setDate(date.getDate() + 3 - (date.getDay() + 6) % 7);
		const week1 = new Date(date.getFullYear(), 0, 4);
		const weekNum = 1 + Math.round(((date - week1) / 86400000 - 3 + (week1.getDay() + 6) % 7) / 7);
		return date.getFullYear() + '-W' + String(weekNum).padStart(2, '0');
	}
	function setPeriodInputType(input, periodType, resetValue){
		const now = new Date();
		input.hidden = (periodType === 'TODOS');
		if (periodType === 'DIA') { input.type = 'date'; if (resetValue) input.value = now.toISOString().slice(0, 10); }
		else if (periodType === 'SEMANA') { input.type = 'week'; if (resetValue) input.value = isoWeekString(now); }
		else if (periodType === 'ANO') { input.type = 'number'; input.min = '2000'; input.max = String(now.getFullYear() + 1); if (resetValue) input.value = String(now.getFullYear()); }
		else if (periodType === 'TODOS') { if (resetValue) input.value = ''; }
		else { input.type = 'month'; if (resetValue) input.value = now.toISOString().slice(0, 7); }
	}
	document.querySelectorAll('[data-period-target]').forEach(function(typeSelect){
		const valueInput = document.getElementById(typeSelect.dataset.periodTarget);
		if (!valueInput) return;
		setPeriodInputType(valueInput, typeSelect.value, false);
		typeSelect.addEventListener('change', function(){
			setPeriodInputType(valueInput, this.value, true);
			const form = typeSelect.closest('form');
			if (form) form.requestSubmit ? form.requestSubmit() : form.submit();
		});
	});
});
