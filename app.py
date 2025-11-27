import streamlit as st
import json
import time
from datetime import datetime
from github import Github, GithubException
import pandas as pd

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Reserva de Livros - Villa",
    page_icon="📚",
    layout="wide"
)

# --- CLASSE DE CONEXÃO COM GITHUB ---
class GitHubConnection:
    def __init__(self):
        """
        Inicializa a conexão usando os segredos definidos no .streamlit/secrets.toml
        Variáveis esperadas: GH_TOKEN, GH_REPO, GH_PATH, GH_BRANCH
        """
        try:
            self.token = st.secrets["GH_TOKEN"]
            self.repo_name = st.secrets["GH_REPO"]
            self.file_path = st.secrets["GH_PATH"]
            self.branch = st.secrets["GH_BRANCH"]
            
            # Conexão com a API
            self.g = Github(self.token)
            self.repo = self.g.get_repo(self.repo_name)
        except Exception as e:
            st.error(f"❌ Erro crítico na configuração dos Segredos: {e}")
            st.stop()

    def get_data(self):
        """
        Lê o arquivo JSON do repositório.
        Retorna: (dict_dados, sha_do_arquivo)
        """
        try:
            contents = self.repo.get_contents(self.file_path, ref=self.branch)
            json_data = json.loads(contents.decoded_content.decode("utf-8"))
            return json_data, contents.sha
        except Exception as e:
            # Se der erro (ex: arquivo não existe 404), retorna estrutura vazia padrão
            # Isso permite que o app funcione mesmo antes do primeiro commit do JSON
            st.warning(f"⚠️ Arquivo de dados não encontrado ou ilegível. Uma nova estrutura será criada ao salvar.")
            return {"books": [], "reservations": []}, None

    def update_data(self, new_data, sha, commit_message="Update via Streamlit"):
        """
        Envia os dados atualizados para o GitHub.
        """
        try:
            json_content = json.dumps(new_data, indent=2, ensure_ascii=False)
            
            if sha:
                # Atualiza arquivo existente
                self.repo.update_file(
                    path=self.file_path,
                    message=commit_message,
                    content=json_content,
                    sha=sha,
                    branch=self.branch
                )
            else:
                # Cria arquivo se não existir (ou se o SHA for None)
                self.repo.create_file(
                    path=self.file_path,
                    message=commit_message,
                    content=json_content,
                    branch=self.branch
                )
            return True
        except GithubException as e:
            st.error(f"❌ Erro ao salvar no GitHub: {e}")
            return False

# --- GERENCIAMENTO DE SESSÃO ---
if 'user' not in st.session_state:
    st.session_state.user = None

def login_family(parent, student, grade):
    if parent and student and grade:
        st.session_state.user = {
            'type': 'family',
            'parent': parent,
            'student': student,
            'grade': grade
        }
        st.rerun()
    else:
        st.warning("Preencha todos os campos.")

def login_admin(password):
    if password == "villa123": # Senha definida no PRD
        st.session_state.user = {'type': 'admin'}
        st.rerun()
    else:
        st.error("Senha incorreta.")

def logout():
    st.session_state.user = None
    st.rerun()

# --- INTERFACE PRINCIPAL ---
def main():
    # Inicializa conexão
    db = GitHubConnection()

    # Cabeçalho Visual
    st.markdown("""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; color: white; text-align: center; margin-bottom: 25px;'>
        <h1>📚 Sistema de Reserva de Livros</h1>
        <p>Ambiente Seguro | Grupo Perfil</p>
    </div>
    """, unsafe_allow_html=True)

    # 1. TELA DE LOGIN
    if st.session_state.user is None:
        c1, c2 = st.columns(2, gap="large")
        
        with c1:
            st.subheader("👨‍👩‍👧‍👦 Acesso Família")
            with st.form("login_family"):
                parent_in = st.text_input("Nome do Responsável")
                student_in = st.text_input("Nome do Estudante")
                grade_in = st.selectbox("Série do Aluno", ["1", "2", "3", "4", "5", "6", "7", "8", "9"])
                if st.form_submit_button("Entrar", type="primary"):
                    login_family(parent_in, student_in, grade_in)

        with c2:
            st.subheader("🛡️ Área Administrativa")
            with st.form("login_admin"):
                pass_in = st.text_input("Senha Admin", type="password")
                if st.form_submit_button("Acessar Painel"):
                    login_admin(pass_in)

    # 2. PAINEL DA FAMÍLIA
    elif st.session_state.user['type'] == 'family':
        user = st.session_state.user
        
        # Barra superior
        col_info, col_btn = st.columns([4, 1])
        col_info.info(f"👤 Responsável: **{user['parent']}** | Aluno: **{user['student']}** ({user['grade']}º Ano)")
        if col_btn.button("Sair"):
            logout()

        st.divider()
        st.subheader(f"📖 Livros Disponíveis para o {user['grade']}º Ano")

        # Buscar dados em tempo real
        with st.spinner("Buscando livros disponíveis..."):
            data, sha = db.get_data()

        # Lógica de Filtragem
        books_for_grade = [b for b in data.get('books', []) if b['grade'] == user['grade']]
        available_books = [b for b in books_for_grade if b['available']]

        if not available_books:
            if not books_for_grade:
                st.warning("Ainda não há livros cadastrados para esta série.")
            else:
                st.warning("⚠️ Todos os livros desta série já foram reservados.")
        else:
            # Exibição em Cards
            for book in available_books:
                with st.container(border=True):
                    c_txt, c_act = st.columns([3, 1])
                    with c_txt:
                        st.markdown(f"### {book['title']}")
                        st.caption(f"Autor: {book['author']} | Matéria: {book['subject']}")
                    
                    with c_act:
                        st.write("") # Espaçamento
                        if st.button(f"RESERVAR", key=f"btn_{book['id']}", type="primary"):
                            # --- Lógica Crítica de Transação ---
                            book_index = next((i for i, b in enumerate(data['books']) if b['id'] == book['id']), -1)
                            
                            if book_index != -1 and data['books'][book_index]['available']:
                                # 1. Atualiza estado do livro
                                data['books'][book_index]['available'] = False
                                data['books'][book_index]['reserved_by'] = user['parent']
                                
                                # 2. Cria registro de reserva
                                new_reservation = {
                                    "id": int(time.time()),
                                    "parent_name": user['parent'],
                                    "student_name": user['student'],
                                    "grade": user['grade'],
                                    "book_title": book['title'],
                                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                data['reservations'].append(new_reservation)

                                # 3. Commit no GitHub
                                with st.spinner("Confirmando reserva no sistema..."):
                                    if db.update_data(data, sha, f"Reserva: {book['title']} - {user['student']}"):
                                        st.success("✅ Reserva confirmada com sucesso!")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("Erro ao comunicar com o servidor. Tente novamente.")
                            else:
                                st.error("Desculpe, este livro acabou de ser reservado por outra pessoa.")
                                time.sleep(2)
                                st.rerun()

    # 3. PAINEL ADMIN
    elif st.session_state.user['type'] == 'admin':
        st.success("🔒 Painel de Gestão")
        if st.button("Sair do Admin", type="secondary"):
            logout()

        # Carregar dados
        data, sha = db.get_data()
        
        tab1, tab2, tab3 = st.tabs(["➕ Cadastrar Livros", "📋 Lista de Reservas", "📊 Estoque"])

        with tab1:
            st.markdown("### Adicionar Novo Título")
            with st.form("add_book_form"):
                col_a, col_b = st.columns(2)
                title = col_a.text_input("Título do Livro")
                author = col_b.text_input("Autor")
                
                col_c, col_d = st.columns(2)
                grade_sel = col_c.selectbox("Série Destino", ["1", "2", "3", "4", "5", "6", "7", "8", "9"])
                subject = col_d.text_input("Disciplina/Matéria")

                if st.form_submit_button("Salvar no Sistema"):
                    if title and subject:
                        new_id = int(time.time()) # ID baseado em timestamp
                        new_book = {
                            "id": new_id,
                            "title": title,
                            "author": author,
                            "grade": grade_sel,
                            "subject": subject,
                            "available": True,
                            "reserved_by": None
                        }
                        
                        # Garante que a lista existe
                        if 'books' not in data: data['books'] = []
                        
                        data['books'].append(new_book)
                        
                        if db.update_data(data, sha, f"Admin add: {title}"):
                            st.success("Livro cadastrado!")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.error("Preencha pelo menos Título e Matéria.")

        with tab2:
            st.markdown("### Histórico de Reservas")
            reservations = data.get('reservations', [])
            if reservations:
                df_res = pd.DataFrame(reservations)
                st.dataframe(
                    df_res[['timestamp', 'grade', 'student_name', 'book_title', 'parent_name']],
                    column_config={
                        "timestamp": "Data/Hora",
                        "grade": "Série",
                        "student_name": "Aluno",
                        "book_title": "Livro",
                        "parent_name": "Responsável"
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Nenhuma reserva registrada até o momento.")

        with tab3:
            st.markdown("### Visão Geral do Estoque")
            books = data.get('books', [])
            if books:
                df_books = pd.DataFrame(books)
                
                # Métricas
                total = len(df_books)
                disponiveis = len(df_books[df_books['available'] == True])
                reservados = total - disponiveis
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Cadastrado", total)
                m2.metric("Disponíveis", disponiveis)
                m3.metric("Reservados", reservados)
                
                st.divider()
                st.dataframe(
                    df_books[['grade', 'title', 'subject', 'available', 'reserved_by']],
                    column_config={
                        "available": st.column_config.CheckboxColumn("Disp.", disabled=True),
                        "grade": "Série",
                        "title": "Título",
                        "subject": "Matéria",
                        "reserved_by": "Reservado Por"
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.write("Nenhum livro cadastrado.")

if __name__ == "__main__":
    main()
