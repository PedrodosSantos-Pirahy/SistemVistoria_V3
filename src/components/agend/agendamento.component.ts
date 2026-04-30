import { Component as NgComponent, signal as ngSignal, computed as ngComputed, inject, effect, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { ApiService } from '../../services/app.service';

interface IntervaloOcupado {
  inicio: string;
  fim: string;
  derivado: boolean;
}

@NgComponent({
  selector: 'app-agendamento',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './agendamento.component.html'
})
export class AgendamentoComponent implements OnInit {

  private apiService: ApiService = inject(ApiService);
  private http: HttpClient = inject(HttpClient);
  readonly minDate = new Date().toISOString().split('T')[0];

  // --- ESTADOS ---
  selectedDate  = ngSignal(new Date().toISOString().split('T')[0]);
  selectedLocal = ngSignal<string | null>(null);

  placa     = ngSignal('');
  preordens = ngSignal<string[]>(['']);
  duracao   = ngSignal(15); // fixo em 15 min — sem dropdown
  horaSelecionada = ngSignal<string | null>(null);

  transportadora = ngSignal<string | null>(null);

  // Controle de UI
  isSearchingPlaca = ngSignal(false);
  placaError       = ngSignal<string | null>(null);
  isSubmitting     = ngSignal(false);

  // true quando o cargo do usuário contém 'COM' (Comercial/Derivados)
  isComercial = ngSignal(false);

  // Placa opcional
  semPlaca          = ngSignal(false);
  transportadoraManual = ngSignal('');
  buscaTranspInput  = ngSignal('');
  sugestoesTransp   = ngSignal<{codigo: string, nome: string}[]>([]);

  // Intervalos ocupados do dia (vindos do banco)
  ocupacoesDoDia = ngSignal<IntervaloOcupado[]>([]);

  constructor() {
    // allowSignalWrites necessário porque carregarOcupacoes chama horaSelecionada.set()
    // dentro do contexto reativo do effect — sem isso Angular lança NG0600 em runtime.
    effect(() => {
      const data  = this.selectedDate();
      const local = this.selectedLocal();
      if (data && local) {
        this.carregarOcupacoes(data, local);
      }
    }, { allowSignalWrites: true });
  }

  ngOnInit() {
    const dados = localStorage.getItem('usuario_logado');
    if (dados) {
      const user = JSON.parse(dados);
      const cargo = (user.cargo || '').trim().toUpperCase();
      this.isComercial.set(cargo.includes('COM'));
      // Local não é auto-preenchido — todos escolhem livremente na tela
    }
  }

  // --- BUSCA DADOS NO BACKEND ---
  carregarOcupacoes(data: string, local: string) {
    this.horaSelecionada.set(null);
    this.apiService.getAgendamentosDia(data, local).subscribe({
      next: (dados) => this.ocupacoesDoDia.set(dados),
      error: (err)  => console.error('Erro ao buscar ocupação', err)
    });
  }

  // --- HELPERS DE TEMPO ---
  private timeToMinutes(time: string): number {
    const [h, m] = time.split(':').map(Number);
    return h * 60 + m;
  }

  reloadPage() { window.location.reload(); }

  terminoPrevisto = ngComputed(() => {
    if (!this.horaSelecionada()) return '--:--';
    const totalMinutos = this.timeToMinutes(this.horaSelecionada()!) + 15;
    const hours   = Math.floor(totalMinutos / 60).toString().padStart(2, '0');
    const minutes = (totalMinutos % 60).toString().padStart(2, '0');
    return `${hours}:${minutes}`;
  });

  // Gera os slots de horário conforme o perfil do usuário.
  // Padrão (não-COM): 08:30–11:45 e 13:30–17:00, máx 1 por slot.
  // Comercial (COM):  08:00–17:00 completo,       máx 1 por slot.
  slots = ngComputed(() => {
    const ocupacoes  = this.ocupacoesDoDia();
    const now        = new Date();
    const isToday    = this.selectedDate() === now.toISOString().split('T')[0];
    const currentMin = now.getHours() * 60 + now.getMinutes();
    const comercial  = this.isComercial();

    // Monta lista de horários conforme perfil
    const horarios: string[] = [];

    if (comercial) {
      // 08:00 até 17:00 a cada 15 min
      for (let h = 8; h <= 17; h++) {
        for (const m of ['00', '15', '30', '45']) {
          const t = `${h.toString().padStart(2, '0')}:${m}`;
          if (this.timeToMinutes(t) <= 17 * 60) horarios.push(t);
        }
      }
    } else {
      // Manhã: 08:30 até 11:45
      for (let h = 8; h <= 11; h++) {
        for (const m of ['00', '15', '30', '45']) {
          if (h === 8 && (m === '00')) continue; // pula 08:00
          const t = `${h.toString().padStart(2, '0')}:${m}`;
          horarios.push(t);
        }
      }
      // Tarde: 13:30 até 17:00
      for (let h = 13; h <= 17; h++) {
        for (const m of ['00', '15', '30', '45']) {
          if (h === 13 && (m === '00' || m === '15')) continue; // pula 13:00 e 13:15
          if (h === 17 && m !== '00') continue; // só 17:00
          const t = `${h.toString().padStart(2, '0')}:${m}`;
          horarios.push(t);
        }
      }
    }

    return horarios.map(slotTimeStr => {
      const slotMin = this.timeToMinutes(slotTimeStr);

      const isPast = isToday && slotMin < currentMin;

      let load = 0;
      for (const ocupacao of ocupacoes) {
        // Conta apenas agendamentos do mesmo tipo de carga:
        // Comercial vê só ocupações de derivados, Expedição vê só fardos.
        if (ocupacao.derivado !== comercial) continue;
        const inicioMin = this.timeToMinutes(ocupacao.inicio);
        const fimMin    = this.timeToMinutes(ocupacao.fim);
        if (slotMin >= inicioMin && slotMin < fimMin) load++;
      }

      return { time: slotTimeStr, load, isPast };
    });
  });

  isFormValid = ngComputed(() => {
    if (!this.selectedLocal() || !this.horaSelecionada()) return false;
    if (this.semPlaca()) {
      if (!this.transportadoraManual().trim()) return false;
    } else {
      if (!this.placa() || !this.transportadora()) return false;
    }
    const ordensValidas = this.preordens().filter((o: string) => o && o.trim().length > 0);
    return ordensValidas.length > 0;
  });

  // --- MÉTODOS DE AÇÃO ---

  formatarPlaca(val: string) {
    let limpa = val.toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (limpa.length > 3) limpa = limpa.slice(0, 3) + '-' + limpa.slice(3, 7);
    this.placa.set(limpa);
    this.transportadora.set(null);
    this.placaError.set(null);
    if (limpa.length >= 8) this.buscarTransportadora(limpa);
  }

  buscarTransportadora(placa: string) {
    this.isSearchingPlaca.set(true);
    this.placaError.set(null);
    this.apiService.consultarPlaca(placa.replace('-', '')).subscribe({
      next: (res) => {
        this.transportadora.set(res.transportadora);
        this.isSearchingPlaca.set(false);
      },
      error: () => {
        this.transportadora.set(null);
        this.placaError.set('Veículo não cadastrado. Proibido agendar.');
        this.isSearchingPlaca.set(false);
      }
    });
  }

  toggleSemPlaca(val: boolean) {
    this.semPlaca.set(val);
    if (val) {
      this.placa.set('');
      this.transportadora.set(null);
      this.placaError.set(null);
      this.transportadoraManual.set('');
      this.buscaTranspInput.set('');
      this.sugestoesTransp.set([]);
    }
  }

  buscarTransportadorasManual(q: string) {
    this.buscaTranspInput.set(q);
    if (q.trim().length < 2) { this.sugestoesTransp.set([]); return; }
    this.apiService.buscarTransportadoras(q).subscribe({
      next: (res) => this.sugestoesTransp.set(res),
      error: () => this.sugestoesTransp.set([])
    });
  }

  selecionarTransportadora(nome: string) {
    this.transportadoraManual.set(nome);
    this.buscaTranspInput.set(nome);
    this.sugestoesTransp.set([]);
  }

  addPreOrdem() {
    if (this.preordens().length >= 5) { alert('⚠️ Máximo de 5 ordens permitido.'); return; }
    this.preordens.update((list: string[]) => [...list, '']);
  }

  removePreOrdem(index: number) {
    this.preordens.update((list: string[]) => list.filter((_: string, i: number) => i !== index));
  }

  updatePreOrdem(index: number, event: Event) {
    const input = event.target as HTMLInputElement;
    let val = input.value.replace(/\D/g, '');
    if (val.length > 6) val = val.slice(0, 6);
    input.value = val;
    this.preordens.update((list: string[]) => {
      const newList = [...list];
      newList[index] = val;
      return newList;
    });
  }

  limparFormulario() {
    this.placa.set('');
    this.preordens.set(['']);
    this.horaSelecionada.set(null);
    this.transportadora.set(null);
    this.semPlaca.set(false);
    this.transportadoraManual.set('');
    this.buscaTranspInput.set('');
    this.sugestoesTransp.set([]);
    this.placaError.set(null);
    if (this.selectedLocal()) {
      this.carregarOcupacoes(this.selectedDate(), this.selectedLocal()!);
    }
  }

  confirmarAgendamento() {
    const semPlaca = this.semPlaca();
    if (!semPlaca && !this.transportadora()) {
      alert('🚫 É obrigatório identificar a transportadora para prosseguir.');
      return;
    }
    if (semPlaca && !this.transportadoraManual().trim()) {
      alert('🚫 Selecione a transportadora na busca.');
      return;
    }
    if (!this.selectedLocal() || !this.horaSelecionada()) {
      alert('Preencha o local e o horário.');
      return;
    }

    const ordensValidas = this.preordens().filter((p: string) => p.trim() !== '');
    if (ordensValidas.length === 0) {
      alert('🚫 É obrigatório informar pelo menos uma Ordem de Carregamento.');
      return;
    }

    const slotSelecionado = this.slots().find((s: {time: string; load: number; isPast: boolean}) => s.time === this.horaSelecionada());
    if (slotSelecionado && slotSelecionado.load >= 1) {
      alert('Este horário acabou de ser ocupado. Por favor, escolha outro.');
      this.carregarOcupacoes(this.selectedDate(), this.selectedLocal()!);
      return;
    }

    this.isSubmitting.set(true);

    const dadosUser = localStorage.getItem('usuario_logado');
    const userObj   = dadosUser ? JSON.parse(dadosUser) : {};

    const payload = {
      placa:              semPlaca ? '' : this.placa(),
      transportadora:     semPlaca ? this.transportadoraManual() : this.transportadora(),
      data_agendamento:   this.selectedDate(),
      hora_inicio:        this.horaSelecionada(),
      duracao_minutos:    15,
      pre_ordens:         ordensValidas,
      local:              this.selectedLocal(),
      status:             'Pendente',
      criado_por:         userObj.nome || 'Sistema',
      derivado:           this.isComercial()
    };

    const enviar = () => {
      this.apiService.criarAgendamento(payload).subscribe({
        next: () => {
          this.isSubmitting.set(false);
          this.limparFormulario();
        },
        error: (err) => {
          this.isSubmitting.set(false);
          if (err.status === 409 || err.error?.error === 'SLOT_OCUPADO') {
            alert('⚠️ Este horário acabou de ser ocupado por outro usuário. Escolha outro.');
            this.horaSelecionada.set(null);
            this.carregarOcupacoes(this.selectedDate(), this.selectedLocal()!);
          } else {
            alert('❌ Erro ao comunicar com o servidor.');
          }
        }
      });
    };

    if (semPlaca) {
      // Sem verificação de duplicidade quando não há placa
      enviar();
    } else {
      const primeiraOrdem = ordensValidas[0];
      const params = `placa=${this.placa()}&data=${this.selectedDate()}&ordem=${primeiraOrdem}&local=${this.selectedLocal()}`;
      this.apiService.verificarDuplicidade(params).subscribe({
        next: (check) => {
          if (check.duplicado) {
            alert('⚠️ ATENÇÃO: Já existe um agendamento para esta PLACA, ORDEM e LOCAL neste DIA!');
            this.isSubmitting.set(false);
            return;
          }
          enviar();
        },
        error: () => this.isSubmitting.set(false)
      });
    }
  }
}
