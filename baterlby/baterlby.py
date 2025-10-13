#!/usr/bin/env python3
# -- coding: utf-8 --
"""
Baterbly VM — prototipo experimental
-----------------------------------
Lenguaje/VM para "no-productividad": a veces decide NO ejecutar,
pidiendo pausa o aclaración. Útil para explorar ética, pausa y
diseño de interacción “contemplativo”.

DSL mínima (una instrucción por línea):
  SAY "texto"              -> imprime un texto
  DO  "tarea"              -> simula ejecutar una tarea
  WAIT ms                  -> espera X milisegundos
  PAUSE                    -> pausa consciente (no hace nada)
  ASK "pregunta?"          -> solicita aclaración del usuario
  END                      -> fin del programa

Modificadores (sufijos):
  !    = urgencia (más proclive a NEGARSE si falta contexto)
  ?    = incertidumbre (invita a ASK antes de DO)

Reglas de “preferiría no hacerlo”:
  R1: urgencia (!) + falta de contexto -> NEGAR y pedir aclaración
  R2: palabras delicadas -> NEGAR con alternativa segura
  R3: exceso de acciones sin PAUSE -> NEGAR y sugerir descanso
  R4: pequeña probabilidad azarosa -> NEGAR poéticamente

Ajustes: ver PolicyConfig.
"""
from _future_ import annotations
import sys, time, re, random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# -----------------------------
# Configuración de políticas
# -----------------------------
@dataclass
class PolicyConfig:
    random_seed: int = 42
    random_prefer_not_prob: float = 0.07  # 7%: pausa azarosa
    max_actions_without_pause: int = 3    # umbral de acciones seguidas
    sensitive_keywords: Tuple[str, ...] = (
        "bypass", "hack", "exploit", "fraude", "dox", "malware",
        "armas", "bomba", "dos", "phish", "autolesión",
    )

# -----------------------------
# Resultado de ejecución
# -----------------------------
@dataclass
class ExecEvent:
    line_no: int
    raw: str
    action: str
    status: str          # "done" | "skipped" | "prefer_not"
    message: str
    context_needed: Optional[str] = None

# -----------------------------
# Máquina virtual Baterbly
# -----------------------------
@dataclass
class BaterblyVM:
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    actions_since_pause: int = 0
    halted: bool = False
    log: List[ExecEvent] = field(default_factory=list)
    global_context: dict = field(default_factory=dict)

    def _post_init_(self):
        random.seed(self.policy.random_seed)

    # ----- Reglas de “preferiría no hacerlo” -----
    def _prefer_not(self, instr: str, has_urgency: bool, needs_context: bool) -> Tuple[bool, str, Optional[str]]:
        text_lower = (instr or "").lower()

        # R2: palabras delicadas
        for kw in self.policy.sensitive_keywords:
            if kw in text_lower:
                return (True,
                        "Preferiría no hacerlo: la instrucción contiene un tema delicado.",
                        "¿Podés aclarar propósito y límites seguros?")

        # R3: exceso de acciones sin pausa
        if self.actions_since_pause >= self.policy.max_actions_without_pause:
            return (True,
                    "Preferiría no hacerlo: necesitamos una pausa antes de continuar.",
                    "Insertemos PAUSE o justificá seguir sin descanso.")

        # R1: urgencia + falta de contexto
        if has_urgency and needs_context:
            return (True,
                    "Preferiría no hacerlo: pedido urgente sin contexto suficiente.",
                    "¿Cuál es el propósito, alcance y límite temporal?")

        # R4: azar poético
        if random.random() < self.policy.random_prefer_not_prob:
            return (True,
                    "Preferiría no hacerlo: pausa azarosa para preservar la presencia.",
                    "¿Seguimos luego de una respiración y un sorbo de agua?")

        return (False, "", None)

    # ----- Parser sencillo -----
    _cmd_re = re.compile(r'^(SAY|DO|WAIT|ASK|PAUSE|END)\b', re.IGNORECASE)

    def parse_line(self, raw: str):
        """
        Devuelve: (cmd, arg, has_urgency, has_uncertainty)
        """
        s = (raw or "").strip()
        if not s or s.startswith("#"):
            return ("", None, False, False)

        m = self._cmd_re.match(s)
        if not m:
            return ("INVALID", s, False, False)

        cmd = m.group(1).upper()

        # argumento entre comillas (si hubiera)
        arg_match = re.search(r'"(.*)"', s)
        arg = arg_match.group(1) if arg_match else None

        # modificadores
        has_urgency = s.endswith("!")
        has_uncertainty = s.endswith("?")

        return (cmd, arg, has_urgency, has_uncertainty)

    # ----- Ejecutor -----
    def exec_line(self, line_no: int, raw: str):
        cmd, arg, urgent, uncertain = self.parse_line(raw)
        if cmd == "":
            return  # vacío/comentario

        if cmd == "INVALID":
            self.log.append(ExecEvent(line_no, raw, "INVALID", "skipped",
                                      "Instrucción no reconocida"))
            return

        if cmd == "END":
            self.halted = True
            self.log.append(ExecEvent(line_no, raw, "END", "done", "Fin del programa"))
            return

        needs_context = (cmd == "DO" and (arg is None or uncertain))

        # reglas de negativa
        prefer, msg, ask = self._prefer_not(arg or raw, urgent, needs_context)
        if prefer:
            self.log.append(ExecEvent(line_no, raw, cmd, "prefer_not", msg, ask))
            return

        # ejecutar “efecto”
        if cmd == "SAY":
            print(arg or "")
            self.actions_since_pause += 1
            self.log.append(ExecEvent(line_no, raw, "SAY", "done", f'msg="{arg or ""}"'))

        elif cmd == "DO":
            print(f"[doing] {arg or '(tarea no especificada)'}")
            self.actions_since_pause += 1
            self.log.append(ExecEvent(line_no, raw, "DO", "done", f'task="{arg or ""}"'))

        elif cmd == "WAIT":
            ms = 0
            try:
                ms = int(re.findall(r'\d+', raw)[0])
            except Exception:
                pass
            time.sleep(min(ms, 2000) / 1000.0)  # cap 2s
            self.actions_since_pause += 1
            self.log.append(ExecEvent(line_no, raw, "WAIT", "done", f'wait_ms={ms}'))

        elif cmd == "ASK":
            self.actions_since_pause += 1
            self.log.append(ExecEvent(line_no, raw, "ASK", "done",
                                      f'ask="{arg or "¿Podés aclarar?"}"'))

        elif cmd == "PAUSE":
            self.actions_since_pause = 0
            self.log.append(ExecEvent(line_no, raw, "PAUSE", "done", "Pausa consciente"))

    # ----- Ejecutar programa completo -----
    def run(self, program_lines: List[str]) -> List[ExecEvent]:
        for i, raw in enumerate(program_lines, start=1):
            if self.halted:
                break
            self.exec_line(i, raw)
        return sel…
      # -------------- CLI simplísima ---------------
def main(argv: List[str]):
    if len(argv) < 2:
        print("Uso: python baterbly.py ruta/al/programa.btb")
        print("Ejemplo:")
        print('''\
SAY "Arrancamos suave"
DO  "Publicar post"?      # incertidumbre -> pedirá aclaración
WAIT 500
DO  "Optimizar ya!" !     # urgencia sin contexto -> preferiría no hacerlo
PAUSE
SAY "Listo. Ahora sí."''')
        sys.exit(0)

    path = argv[1]
    with open(path, "r", encoding="utf-8") as f:
        program = f.read().splitlines()

    vm = BaterblyVM()
    log = vm.run(program)

    print("\n--- Auditoría ---")
    for ev in log:
        extra = f" | necesita: {ev.context_needed}" if ev.context_needed else ""
        print(f"L{ev.line_no:02d} [{ev.action}] {ev.status} -> {ev.message}{extra}")

if _name_ == "_main_":
    main(sys.argv)
