import { Component as NgComponent, signal as ngSignal, computed as ngComputed, inject, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';

// Interface para o retorno do backend
interface IntervaloOcupado {
  inicio: string;
  fim: string;
}

@NgComponent({
  selector: 'app-agendamento',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './agendamento.component.html'
})
export class AgendamentoComponent {
  private http: HttpClient = inject(HttpClient);
  private router: Router = inject(Router);
  readonly minDate = new Date().toISOString().split('T')[0];

  // --- ESTADOS ---
  selectedDate = ngSignal(new Date().toISOString().split('T')[0]);
  selectedLocal = ngSignal<string | null>(null);
  
  placa = ngSignal('');
  preordens = ngSignal<string[]>(['']); 
  duracao = ngSignal(30); 
  horaSelecionada = ngSignal<string | null>(null);
  
  transportadora = ngSignal<string | null>(null);
  
  // Controle de UI
  isSearchingPlaca = ngSignal(false);
  placaError = ngSignal<string | null>(null);
  isSubmitting = ngSignal(false); 

  // 🔥 Armazena os intervalos ocupados do dia (vindo do banco)
  ocupacoesDoDia = ngSignal<IntervaloOcupado[]>([]);

  constructor() {
    // 🔥 EFEITO AUTOMÁTICO:
    // Sempre que 'selectedDate' mudar, busca os agendamentos do banco.
    effect(() => {
      const data = this.selectedDate();
      if (data) {
        this.carregarOcupacoes(data);
      }
    });
  }

  // --- BUSCA DADOS NO BACKEND ---
  carregarOcupacoes(data: string) {
    // Reseta hora selecionada ao mudar de dia para evitar conflitos visuais
    this.horaSelecionada.set(null);
    
    // Chama o endpoint novo que filtra os cancelados
    this.http.get<IntervaloOcupado[]>(`http://192.168.53.193:5002/agendamentos-dia?data=${data}`)
      .subscribe({
        next: (dados) => {
          this.ocupacoesDoDia.set(dados);
        },
        error: (err) => console.error('Erro ao buscar ocupação', err)
      });
  }

  // --- HELPERS DE TEMPO ---
  private timeToMinutes(time: string): number {
    const [h, m] = time.split(':').map(Number);
    return h * 60 + m;
  }

  // --- COMPUTEDS (A Lógica Pesada) ---
  reloadPage() {
    window.location.reload();
  }
  terminoPrevisto = ngComputed(() => {
    if (!this.horaSelecionada()) return '--:--';
    const totalMinutos = this.timeToMinutes(this.horaSelecionada()!) + Number(this.duracao());
    const hours = Math.floor(totalMinutos / 60).toString().padStart(2, '0');
    const minutes = (totalMinutos % 60).toString().padStart(2, '0');
    return `${hours}:${minutes}`;
  });

  // 🔥 CALCULA A LOTAÇÃO DOS SLOTS COM BASE NO BANCO
  slots = ngComputed(() => {
    const times = [];
    const ocupacoes = this.ocupacoesDoDia(); // Dados reais do banco
    const now = new Date();
    const isToday = this.selectedDate() === now.toISOString().split('T')[0];
    const currentHour = now.getHours();
    const currentMinute = now.getMinutes();

    for (let h = 8; h <= 17; h++) {
      for (let m of ['00', '15', '30', '45']) {
        const slotTimeStr = `${h.toString().padStart(2, '0')}:${m}`;
        const slotMin = this.timeToMinutes(slotTimeStr);

        // 1. Verifica se já passou (se for hoje)
        let isPast = false;
        if (isToday) {
           if (h < currentHour || (h === currentHour && Number(m) < currentMinute)) {
             isPast = true;
           }
        }

        // 2. Calcula Carga (Quantos caminhões estarão lá neste horário?)
        // Regra: O slot está ocupado se: InicioAgendamento <= Slot < FimAgendamento
        let load = 0;
        
        for (const ocupacao of ocupacoes) {
           const inicioMin = this.timeToMinutes(ocupacao.inicio);
           const fimMin = this.timeToMinutes(ocupacao.fim);

           // Se o horário do slot cai dentro de um agendamento existente
           if (slotMin >= inicioMin && slotMin < fimMin) {
             load++;
           }
        }

        times.push({ 
          time: slotTimeStr, 
          load: load, // Número real de caminhões simultâneos
          isPast: isPast 
        });
      }
    }
    return times;
  });
  // --- COMPUTEDS ---

  // 🔥 VALIDAÇÃO EM TEMPO REAL
  isFormValid = ngComputed(() => {
    // 1. Tem Local e Hora?
    if (!this.selectedLocal() || !this.horaSelecionada()) return false;
    
    // 2. Tem Placa e Transportadora Validada?
    if (!this.placa() || !this.transportadora()) return false;
    
    // 3. 🔥 TEM PELO MENOS UMA ORDEM VÁLIDA (NÃO VAZIA)?
    const ordensValidas = this.preordens().filter(ordem => ordem && ordem.trim().length > 0);
    if (ordensValidas.length === 0) return false;

    return true; // Tudo ok!
  });

  // ... (mantenha os outros computeds como slots e terminoPrevisto)

  // --- MÉTODOS DE AÇÃO ---

  formatarPlaca(val: string) {
    let limpa = val.toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (limpa.length > 3) limpa = limpa.slice(0, 3) + '-' + limpa.slice(3, 7);
    this.placa.set(limpa);
    this.transportadora.set(null);
    this.placaError.set(null);
    if (limpa.length >= 8) {
      this.buscarTransportadora(limpa);
    }
  }

  buscarTransportadora(placa: string) {
    this.isSearchingPlaca.set(true);
    this.placaError.set(null);
    const placaEnvio = placa.replace('-', '');

    this.http.get<{ transportadora: string }>(`http://192.168.53.193:5000/consultar-placa/${placaEnvio}`)
      .subscribe({
        next: (res) => {
          this.transportadora.set(res.transportadora);
          this.isSearchingPlaca.set(false);
        },
        error: (err) => {
          this.transportadora.set(null);
          this.placaError.set('Veículo não cadastrado. Proibido agendar.');
          this.isSearchingPlaca.set(false);
        }
      });
  }

  addPreOrdem() { 
    if (this.preordens().length >= 5) {
      alert('⚠️ Máximo de 5 ordens permitido.');
      return; // Impede adicionar mais
    }
    this.preordens.update(list => [...list, '']); 
  }
  removePreOrdem(index: number) { this.preordens.update(list => list.filter((_, i) => i !== index)); }
  
  updatePreOrdem(index: number, event: Event) {
    const input = event.target as HTMLInputElement;
    let val = input.value.replace(/\D/g, ''); 
    if (val.length > 6) val = val.slice(0, 6);
    input.value = val; 
    this.preordens.update(list => {
      const newList = [...list];
      newList[index] = val;
      return newList;
    });
  }

  confirmarAgendamento() {
    // 1. Validações Básicas (Front)
    if (!this.transportadora()) {
      alert('🚫 É obrigatório identificar a transportadora para prosseguir.');
      return;
    }
    if (!this.selectedLocal() || !this.horaSelecionada()) {
      alert('Preencha o local e o horário.');
      return;
    }

    const ordensValidas = this.preordens().filter(p => p.trim() !== '');
    if (ordensValidas.length === 0) {
        alert('🚫 É obrigatório informar pelo menos uma Ordem de Carregamento.');
        return;
    }
    
    // Validação de Lotação (Front)
    const slotSelecionado = this.slots().find(s => s.time === this.horaSelecionada());
    if (slotSelecionado && slotSelecionado.load >= 3) {
      alert('Este horário acabou de lotar. Por favor, escolha outro.');
      this.carregarOcupacoes(this.selectedDate());
      return;
    }

    this.isSubmitting.set(true);

    // 🔥 2. VALIDAÇÃO DE DUPLICIDADE LEVE (BACKEND)
    // Verifica: Placa + Data + Ordem1 (Ignora Hora)
    const primeiraOrdem = ordensValidas[0];
    const params = `placa=${this.placa()}&data=${this.selectedDate()}&ordem=${primeiraOrdem}`;

    this.http.get<{ duplicado: boolean }>(`http://192.168.53.193:5002/verificar-duplicidade?${params}`)
      .subscribe({
        next: (check) => {
          
          if (check.duplicado) {
            alert(`⚠️ ATENÇÃO: Já existe um agendamento para esta PLACA e ORDEM neste DIA!\n\nVerifique se não está duplicando o cadastro.`);
            this.isSubmitting.set(false);
            return; // ⛔ BLOQUEIA O ENVIO
          }

          // --- SE NÃO FOR DUPLICADO, SEGUE O BAILE ---
          const payload = {
            placa: this.placa(),
            transportadora: this.transportadora(),
            data_agendamento: this.selectedDate(),
            hora_inicio: this.horaSelecionada(),
            duracao_minutos: this.duracao(),
            pre_ordens: ordensValidas,
            local: this.selectedLocal(),
            status: 'Pendente' 
          };

          this.http.post('http://192.168.53.193:5000/criar-agendamento', payload)
            .subscribe({
              next: (res: any) => {
                alert('✅ Agendamento realizado com sucesso!');
                this.isSubmitting.set(false);
                this.router.navigate(['/monitoramento']); 
              },
              error: (err) => {
                console.error('Erro ao agendar:', err);
                alert('❌ Erro ao comunicar com o servidor.');
                this.isSubmitting.set(false);
              }
            });

        },
        error: () => {
          console.warn('Falha na verificação de duplicidade, tentando criar mesmo assim...');
          // Se a verificação falhar (ex: erro de rede no GET leve), 
          // libera o POST para não travar a operação.
          this.isSubmitting.set(false); 
        }
      });
  }
}