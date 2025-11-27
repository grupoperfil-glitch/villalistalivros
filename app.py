import streamlit as st
import json
from github import Github, GithubException
from datetime import datetime
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Reserva de Livros", page_icon="📚", layout="wide")

# --- CONEXÃO COM GITHUB (CAMADA DE PERSISTÊNCIA) ---
class GitHubConnection:
    def __init__(self):
        try:
            self.token = st.secrets["GITHUB_TOKEN"]
            self.repo_name = st.secrets["REPO_NAME"] # Ex: "seu-usuario/seu-repo"
            self.file_path = st.secrets["FILE_PATH"] # Ex: "data/data.json"
            self.g = Github(self.token)
            self.repo = self.g.get_repo(self.repo_name)
        except Exception as e:
            st.error(f"Erro na configuração dos Segredos: {e}")
            st.stop()

    def get_data(self):
        """Lê o arquivo JSON do repositório."""
        try:
            contents = self.repo.get_contents(self.file_path)
            json_data = json.loads(contents.decoded_content.decode("utf-8"))
            return json_data, contents.sha
        except Exception as e:
            # Se o arquivo não existir, retorna estrutura padrão e None para SHA
            st.warning(f"Arquivo de dados não encontrado ou ilegível. Criando nova estrutura. Erro: {e}")
            return {"books": [], "reservations": []}, None

    def update_data(self, new_data, sha, commit_message="Atualização via Streamlit App"):
        """
        Escreve os dados atualizados no repositório.
        ATENÇÃO: Isso sobrescreve o arquivo. Race conditions podem ocorrer.
        """
        try:
            json_content = json.dumps(new_data, indent=2, ensure_ascii=False)
            if sha:
                self.repo.update_file(self.file_path, commit_message, json_content, sha)
            else:
                self.repo.create_file(self.file_path, commit_message, json_content)
            return True
        except GithubException as e:
            st.error(f"Erro ao salvar no GitHub: {e}")
            return False

# --- FUNÇÕES DE LÓGICA DE NEGÓCIO ---

def init_session_state():
    if 'user' not in st.session_state:
        st.session_state.user = None # Estrutura: {'type': 'admin' ou 'family', 'name': ..., 'grade': ...}

def login_family(parent, student, grade):
    if parent and student and grade:
        st.session_state.user = {
            'type': 'family',
            'parent': parent,
            'student': student,
            'grade': grade
        }
        st.rerun()

def login_admin(password):
    if password == "villa123": # Senha conforme PRD
        st.session_state.user = {'type': 'admin'}
        st.rerun()
    else:
        st.error("Senha incorreta.")

def logout():
    st.session_state.user = None
    st.rerun()

# --- INTERFACE DE USUÁRIO (UI) ---

def main():
    init_session_state()
    db = GitHubConnection()

    # Cabeçalho
    st.markdown("""
    <style>
    .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px; text-align: center;}
    </style>
    <div class="header">
        <h1>📚 Sistema de Reserva de Livros</h1>
        <p>Sua escola conectada</p>
    </div>
    """, unsafe_allow_html=True)

    # ---------------- TELA DE LOGIN ----------------
    if st.session_state.user is None:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("👨‍👩‍👧‍👦 Acesso Família")
            parent = st.text_input("Nome do Responsável")
            student = st.text_input("Nome do Estudante")
            grade = st.selectbox("Série", ["1", "2", "3", "4", "5", "6", "7", "8", "9"])
            if st.button("Entrar como Família"):
                login_family(parent, student, grade)

        with col2:
            st.subheader("🛡️ Acesso Admin")
            pwd = st.text_input("Senha", type="password")
            if st.button("Entrar como Admin"):
                login_admin(pwd)

    # ---------------- DASHBOARD FAMÍLIA ----------------
    elif st.session_state.user['type'] == 'family':
        user = st.session_state.user
        st.info(f"Logado como: **{user['parent']}** (Aluno: {user['student']} - {user['grade']}º Ano)")
        
        if st.button("Sair"):
            logout()

        st.divider()
        st.subheader(f"Livros Disponíveis para o {user['grade']}º Ano")

        # Carregar dados frescos
        data, sha = db.get_data()
        
        # Filtrar livros
        available_books = [b for b in data['books'] if b['grade'] == user['grade'] and b['available']]
        
        if not available_books:
            st.warning("Não há livros disponíveis para sua série no momento.")
        else:
            # Grid de livros
            cols = st.columns(3)
            for idx, book in enumerate(available_books):
                with cols[idx % 3]:
                    with st.container(border=True):
                        st.markdown(f"**{book['title']}**")
                        st.caption(f"Autor: {book['author']}")
                        st.caption(f"Matéria: {book['subject']}")
                        
                        if st.button(f"Reservar", key=f"res_{book['id']}"):
                            # Lógica de Reserva (Atomic-ish)
                            book['available'] = False
                            book['reserved_by'] = user['parent']
                            
                            # Adicionar registro de reserva
                            new_reservation = {
                                "id": int(time.time()),
                                "parent_name": user['parent'],
                                "student_name": user['student'],
                                "grade": user['grade'],
                                "book_title": book['title'],
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            data['reservations'].append(new_reservation)
                            
                            # Salvar no GitHub
                            with st.spinner("Processando reserva..."):
                                success = db.update_data(data, sha, f"Reserva: {book['title']} por {user['parent']}")
                                if success:
                                    st.success(f"Livro '{book['title']}' reservado com sucesso!")
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("Erro ao reservar. Tente novamente (alguém pode ter reservado antes).")

    # ---------------- DASHBOARD ADMIN ----------------
    elif st.session_state.user['type'] == 'admin':
        st.success("Painel Administrativo")
        if st.button("Sair", type="primary"):
            logout()

        tab1, tab2, tab3 = st.tabs(["Gerenciar Livros", "Ver Reservas", "Relatórios"])
        
        # Carregar dados frescos uma vez para usar nas abas
        data, sha = db.get_data()

        with tab1:
            st.write("### Adicionar Novo Livro")
            with st.form("add_book"):
                c1, c2 = st.columns(2)
                title = c1.text_input("Título")
                author = c2.text_input("Autor")
                c3, c4 = st.columns(2)
                grade_input = c3.selectbox("Série", ["1", "2", "3", "4", "5", "6", "7", "8", "9"])
                subject = c4.text_input("Matéria")
                
                if st.form_submit_button("Cadastrar Livro"):
                    new_id = len(data['books']) + 1 if data['books'] else 1
                    new_book = {
                        "id": new_id,
                        "title": title,
                        "author": author,
                        "grade": grade_input,
                        "subject": subject,
                        "available": True,
                        "reserved_by": None
                    }
                    data['books'].append(new_book)
                    if db.update_data(data, sha, f"Admin adicionou livro: {title}"):
                        st.success("Livro adicionado!")
                        st.rerun()

            st.write("### Livros Cadastrados")
            st.dataframe(data['books'])

        with tab2:
            st.write("### Reservas Realizadas")
            if data['reservations']:
                st.dataframe(data['reservations'])
            else:
                st.info("Nenhuma reserva encontrada.")

        with tab3:
            st.write("### Estatísticas")
            total_books = len(data['books'])
            reserved = len([b for b in data['books'] if not b['available']])
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total de Livros", total_books)
            col2.metric("Livros Reservados", reserved)
            col3.metric("Disponíveis", total_books - reserved)

            if st.button("Exportar CSV das Reservas"):
                # Simulação de exportação simples
                st.download_button(
                    label="Baixar CSV",
                    data=json.dumps(data['reservations']),
                    file_name="reservas.json",
                    mime="application/json"
                )

if __name__ == "__main__":
    main()
