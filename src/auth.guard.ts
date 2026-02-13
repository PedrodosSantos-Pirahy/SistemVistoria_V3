import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';

export const authGuard: CanActivateFn = (route, state) => {
  // 🔥 CORREÇÃO: Adicione ': Router' aqui
  const router: Router = inject(Router);
  
  const usuarioLogado = localStorage.getItem('usuario_logado');

  if (usuarioLogado) {
    return true;
  } else {
    router.navigate(['/login']);
    return false;
  }
};