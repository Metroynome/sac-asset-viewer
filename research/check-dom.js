JSON.stringify({status:[...document.querySelectorAll('[role=status]')].map(x=>x.textContent),canvas:[...document.querySelectorAll('canvas')].map(x=>({...x.dataset}))})
