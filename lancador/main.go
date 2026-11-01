//go:build windows

// Axtel.exe — abre o Axtel sem janela preta e mostra o painel no navegador.
//
// Se o PC não tiver um Python 3.9+ que funcione, oferece instalar sozinho:
// primeiro pelo winget (Windows 10/11) e, se não der, baixando o instalador oficial do python.org.
// A instalação é só para o usuário atual (não pede administrador).
package main

import (
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	porta        = "8501"
	pythonVersao = "3.12.10"
	pythonURL    = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
	semJanela    = 0x08000000 // CREATE_NO_WINDOW
)

var user32 = syscall.NewLazyDLL("user32.dll")

func caixa(texto string, flags uintptr) int {
	box := user32.NewProc("MessageBoxW")
	t, _ := syscall.UTF16PtrFromString(texto)
	c, _ := syscall.UTF16PtrFromString("Axtel")
	r, _, _ := box.Call(0, uintptr(unsafe.Pointer(t)), uintptr(unsafe.Pointer(c)), flags|0x00010000) // MB_SETFOREGROUND
	return int(r)
}

func aviso(texto string)         { caixa(texto, 0x40) }             // MB_ICONINFORMATION
func erro(texto string)          { caixa(texto, 0x10) }             // MB_ICONERROR
func pergunta(texto string) bool { return caixa(texto, 0x24) == 6 } // MB_YESNO|MB_ICONQUESTION -> IDYES

func aberto() bool {
	c, err := net.DialTimeout("tcp", "127.0.0.1:"+porta, 400*time.Millisecond)
	if err != nil {
		return false
	}
	c.Close()
	return true
}

func abrirNavegador() {
	exec.Command("rundll32", "url.dll,FileProtocolHandler", "http://localhost:"+porta).Start()
}

func escondido(cmd *exec.Cmd) *exec.Cmd {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: semJanela}
	return cmd
}

// testa um Python de verdade (o "python" da Microsoft Store é só um atalho que abre a loja)
// e devolve o caminho do pythonw.exe correspondente.
func testar(exe string, extra ...string) (string, bool) {
	args := append(extra, "-c", "import sys;print(sys.version_info[0],sys.version_info[1]);print(sys.executable)")
	cmd := escondido(exec.Command(exe, args...))
	feito := make(chan []byte, 1)
	go func() {
		out, err := cmd.Output()
		if err != nil {
			out = nil
		}
		feito <- out
	}()
	var out []byte
	select {
	case out = <-feito:
	case <-time.After(15 * time.Second):
		if cmd.Process != nil {
			cmd.Process.Kill()
		}
		return "", false
	}
	linhas := strings.Split(strings.ReplaceAll(strings.TrimSpace(string(out)), "\r", ""), "\n")
	if len(linhas) < 2 {
		return "", false
	}
	v := strings.Fields(linhas[0])
	if len(v) != 2 {
		return "", false
	}
	maior, _ := strconv.Atoi(v[0])
	menor, _ := strconv.Atoi(v[1])
	if maior != 3 || menor < 9 {
		return "", false
	}
	py := strings.TrimSpace(linhas[1])
	w := filepath.Join(filepath.Dir(py), "pythonw.exe")
	if _, err := os.Stat(w); err == nil {
		return w, true
	}
	return py, true
}

// lugares comuns onde o Python fica instalado (o PATH desta janela não vê uma instalação recém-feita)
func pastasConhecidas() []string {
	var achados []string
	for _, base := range []string{
		filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs", "Python"),
		os.Getenv("ProgramFiles"),
		filepath.Join(os.Getenv("LOCALAPPDATA"), "Python"),
	} {
		if base == "" {
			continue
		}
		m, _ := filepath.Glob(filepath.Join(base, "Python3*", "python.exe"))
		achados = append(achados, m...)
		m, _ = filepath.Glob(filepath.Join(base, "pythoncore-3*", "python.exe"))
		achados = append(achados, m...)
	}
	sort.Sort(sort.Reverse(sort.StringSlice(achados))) // versões mais novas primeiro
	return achados
}

func acharPython() (string, bool) {
	if p, err := exec.LookPath("py"); err == nil {
		if w, ok := testar(p, "-3"); ok {
			return w, true
		}
	}
	for _, nome := range []string{"python", "python3"} {
		if p, err := exec.LookPath(nome); err == nil && !strings.Contains(strings.ToLower(p), `\windowsapps\`) {
			if w, ok := testar(p); ok {
				return w, true
			}
		}
	}
	for _, p := range pastasConhecidas() {
		if w, ok := testar(p); ok {
			return w, true
		}
	}
	return "", false
}

func esperar(cmd *exec.Cmd, limite time.Duration) error {
	if err := cmd.Start(); err != nil {
		return err
	}
	feito := make(chan error, 1)
	go func() { feito <- cmd.Wait() }()
	select {
	case err := <-feito:
		return err
	case <-time.After(limite):
		cmd.Process.Kill()
		return fmt.Errorf("demorou demais")
	}
}

func instalarPorWinget() bool {
	w, err := exec.LookPath("winget")
	if err != nil {
		return false
	}
	cmd := escondido(exec.Command(w, "install", "-e", "--id", "Python.Python.3.12", "--scope", "user", "--silent",
		"--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"))
	return esperar(cmd, 12*time.Minute) == nil
}

func instalarPorDownload() error {
	destino := filepath.Join(os.TempDir(), "python-"+pythonVersao+"-amd64.exe")
	cli := &http.Client{Timeout: 10 * time.Minute}
	r, err := cli.Get(pythonURL)
	if err != nil {
		return fmt.Errorf("sem internet ou o site do Python não respondeu (%v)", err)
	}
	defer r.Body.Close()
	if r.StatusCode != 200 {
		return fmt.Errorf("o site do Python respondeu %d", r.StatusCode)
	}
	f, err := os.Create(destino)
	if err != nil {
		return err
	}
	if _, err := io.Copy(f, r.Body); err != nil {
		f.Close()
		return err
	}
	f.Close()
	cmd := exec.Command(destino, "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1",
		"InstallLauncherAllUsers=0", "Include_test=0", "Include_doc=0", "Shortcuts=0")
	if err := esperar(cmd, 15*time.Minute); err != nil {
		return fmt.Errorf("o instalador do Python não terminou (%v)", err)
	}
	os.Remove(destino)
	return nil
}

func instalarPython() (string, bool) {
	if !pergunta("O Axtel precisa do Python (gratuito) e ele não está instalado neste PC.\n\n" +
		"Quer que o Axtel instale agora? Leva de 1 a 5 minutos e precisa de internet.\n" +
		"A instalação é só para o seu usuário e não muda nada no resto do PC.") {
		aviso("Tudo bem. Para usar o Axtel, instale o Python 3.12 pelo site python.org\n" +
			"(marque \"Add python.exe to PATH\") e abra o Axtel de novo.")
		return "", false
	}
	aviso("Vou instalar o Python agora, em segundo plano.\n\nClique em OK e aguarde: quando terminar, o Axtel abre sozinho.")
	if instalarPorWinget() {
		if w, ok := acharPython(); ok {
			return w, true
		}
	}
	if err := instalarPorDownload(); err != nil {
		erro("Não consegui instalar o Python: " + err.Error() + "\n\nInstale pelo site python.org (versão 3.12) e abra o Axtel de novo.")
		return "", false
	}
	if w, ok := acharPython(); ok {
		return w, true
	}
	erro("O Python foi instalado, mas não consegui encontrá-lo.\n\nReinicie o PC e abra o Axtel de novo.")
	return "", false
}

func main() {
	if aberto() { // já está rodando: só abre o painel
		abrirNavegador()
		return
	}
	exe, _ := os.Executable()
	pasta := filepath.Dir(exe)
	script := filepath.Join(pasta, "axtel.py")
	if _, err := os.Stat(script); err != nil {
		erro("Não encontrei o arquivo axtel.py.\n\nO Axtel.exe precisa ficar dentro da pasta do Axtel, junto com os outros arquivos.")
		return
	}
	py, ok := acharPython()
	if !ok {
		if py, ok = instalarPython(); !ok {
			return
		}
	}
	cmd := escondido(exec.Command(py, script, "--sem-navegador"))
	cmd.Dir = pasta
	if err := cmd.Start(); err != nil {
		erro("Não consegui iniciar o Axtel: " + err.Error())
		return
	}
	for i := 0; i < 80; i++ { // espera até 20 s o painel subir
		time.Sleep(250 * time.Millisecond)
		if aberto() {
			abrirNavegador()
			return
		}
	}
	erro("O Axtel não abriu.\n\nVeja o arquivo dados\\axtel.log na pasta do Axtel, ou abra pelo \"Iniciar Axtel (com janela).bat\" para ver a mensagem de erro.")
}
