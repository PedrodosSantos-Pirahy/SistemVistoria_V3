import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/app.service'; // Ajuste o caminho se necessário

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.component.html'
})
export class LoginComponent {
  usuario = '';
  senha = '';
  loading = signal(false);
  erro = signal('');

  // Injeção explícita do ApiService para evitar erros de tipagem
  private apiService: ApiService = inject(ApiService);

  entrar() {
    this.loading.set(true);
    this.erro.set('');
    
    const body = { usuario: this.usuario, senha: this.senha };

    // Substituído: Agora usa o método login() do serviço
    this.apiService.login(body).subscribe({
        next: (res: any) => {
          // Salva os dados do usuário
          localStorage.setItem('usuario_logado', JSON.stringify(res.user));
          // Recarrega para o AppComponent aplicar as permissões
          window.location.reload();
        },
        error: (err: any) => {
          this.loading.set(false);
          this.erro.set(err.error?.error || 'Erro ao conectar.');
        }
      });
  }
}