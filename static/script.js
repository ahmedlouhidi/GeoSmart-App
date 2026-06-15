let global_grs_data = null;

document.getElementById('form-module1').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const btn = document.getElementById('btn-calc-m1');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Calcul en cours...';
    btn.disabled = true;

    const payload = {
        C: document.getElementById('C').value,
        phi: document.getElementById('phi').value,
        gamma: document.getElementById('gamma').value,
        B: document.getElementById('B').value,
        L: document.getElementById('L').value,
        Df: document.getElementById('Df').value,
        F: document.getElementById('F').value,
        FS: document.getElementById('FS').value
    };

    try {
        const response = await fetch('/api/module1', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        if(data.success) {
            displayModule1Result(data.data);
            if(data.data.needs_grs) {
                global_grs_data = data.data;
                document.getElementById('module3').classList.remove('hidden');
            } else {
                document.getElementById('module3').classList.add('hidden');
            }
        } else {
            alert('Erreur: ' + data.message);
        }
    } catch (err) {
        alert('Erreur de connexion');
    }

    btn.innerHTML = originalText;
    btn.disabled = false;
});

function displayModule1Result(data) {
    const resArea = document.getElementById('result-module1');
    
    let html = `
        <div class="result-box">
            <h3>Résultats Capacité Portante (Meyerhof)</h3>
            <div class="grid-2">
                <div class="stat"><span class="stat-label">q_ult_brut:</span> <span class="stat-value">${data.q_ult_brut.toFixed(2)} kPa</span></div>
                <div class="stat"><span class="stat-label">q_net_ult:</span> <span class="stat-value">${data.q_net_ult.toFixed(2)} kPa</span></div>
                <div class="stat"><span class="stat-label">q_admissible:</span> <span class="stat-value">${data.q_ad.toFixed(2)} kPa</span></div>
                <div class="stat"><span class="stat-label">q_appliqué:</span> <span class="stat-value">${data.q_app.toFixed(2)} kPa</span></div>
            </div>
        </div>
    `;

    if(data.needs_grs) {
        html += `
        <div class="alert alert-danger">
            <i class="fa-solid fa-circle-xmark fa-2x"></i>
            <div>
                <strong>Le sol non renforcé NE PEUT PAS supporter la charge.</strong><br>
                Déficit de capacité: ${data.deficit.toFixed(2)} kPa.<br>
                Un renforcement (SGR) est nécessaire.
            </div>
        </div>`;
    } else {
        html += `
        <div class="alert alert-success">
            <i class="fa-solid fa-circle-check fa-2x"></i>
            <div>
                <strong>Le sol non renforcé est SÛR.</strong><br>
                Aucun renforcement n'est requis. La conception est complète.
            </div>
        </div>
        <button class="btn-pdf" onclick="alert('Fonctionnalité en cours de développement : Génération et téléchargement du rapport complet en PDF.')">
            <i class="fa-solid fa-file-pdf"></i> Télécharger le Rapport PDF
        </button>`;
    }

    resArea.innerHTML = html;
    resArea.classList.remove('hidden');
}


document.getElementById('form-module3').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if(!global_grs_data) return;

    const loader = document.getElementById('loader');
    const resArea = document.getElementById('result-module3');
    const btn = document.getElementById('btn-calc-m3');
    
    loader.classList.remove('hidden');
    resArea.classList.add('hidden');
    btn.disabled = true;

    const payload = {
        grs_data: global_grs_data,
        EA: document.getElementById('EA').value,
        UZ_ALLOW: document.getElementById('UZ_ALLOW').value
    };

    try {
        const response = await fetch('/api/module3', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if(data.success) {
            displayModule3Result(data);
        } else {
            alert('Erreur: ' + data.message);
        }
    } catch (err) {
        alert('Erreur lors de l\'optimisation IA');
    }

    loader.classList.add('hidden');
    btn.disabled = false;
});

function displayModule3Result(data) {
    const resArea = document.getElementById('result-module3');
    
    let alertHtml = '';
    if(data.els_ok && data.elu_ok) {
        alertHtml = `
        <div class="alert alert-success">
            <i class="fa-solid fa-shield-check fa-2x"></i>
            <div>
                <strong>Conception SGR Validée !</strong><br>
                La configuration est sûre pour le tassement (ELS) et la capacité portante (ELU).
            </div>
        </div>`;
    } else {
        alertHtml = `
        <div class="alert alert-danger">
            <i class="fa-solid fa-triangle-exclamation fa-2x"></i>
            <div>
                <strong>Attention !</strong><br>
                Les contraintes (ELS/ELU) ne sont pas toutes satisfaites. Vérifiez les paramètres de géogrille.
            </div>
        </div>`;
    }

    let html = `
        <div class="result-box">
            <h3>Configuration Optimale (SGR)</h3>
            <div class="grid-2">
                <div class="stat"><span class="stat-label">Nombre de couches (N):</span> <span class="stat-value">${data.N_opt}</span></div>
                <div class="stat"><span class="stat-label">Surface totale géogrille:</span> <span class="stat-value">${data.surface_opt.toFixed(2)} m²</span></div>
                <div class="stat"><span class="stat-label">Espacement (h):</span> <span class="stat-value">${data.h_opt.toFixed(3)} m</span></div>
                <div class="stat"><span class="stat-label">Prof. 1ère couche (e):</span> <span class="stat-value">${data.e_opt.toFixed(3)} m</span></div>
                <div class="stat"><span class="stat-label">Extension (Lx):</span> <span class="stat-value">${data.Lx_opt.toFixed(3)} m</span></div>
                <div class="stat"><span class="stat-label">Tassement prédit (Uz):</span> <span class="stat-value">${data.uz_opt_mm.toFixed(2)} mm</span></div>
                <div class="stat"><span class="stat-label">q_admissible (SGR):</span> <span class="stat-value">${data.q_ad_SGR.toFixed(2)} kPa</span></div>
            </div>
        </div>
        ${alertHtml}
    `;

    if(data.plot_base64) {
        html += `<img src="data:image/png;base64,${data.plot_base64}" class="plot-image" alt="Courbe Charge-Tassement">`;
    }

    html += `
    <button class="btn-pdf" onclick="alert('Fonctionnalité en cours de développement : Génération et téléchargement du rapport complet en PDF avec graphiques IA.')">
        <i class="fa-solid fa-file-pdf"></i> Télécharger le Rapport PDF
    </button>`;

    resArea.innerHTML = html;
    resArea.classList.remove('hidden');
}
