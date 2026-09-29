const label=[...document.querySelectorAll('dialog label')].find(l=>l.textContent==='Unlit');label.querySelector('input').click();document.querySelector('dialog').innerText.includes('Unlit');
