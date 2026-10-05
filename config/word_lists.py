"""
Word lists used when the app reads job descriptions and CVs (no code here, only data).

To teach the app a new way of writing a skill, add it to SKILL_ALIASES.
"""

# Other ways the same skill is written on CVs.
# The key is the skill name in lower case WITHOUT spaces, dots, dashes, "_" or "/"  ("Node.js" -> "nodejs").
SKILL_ALIASES = {
    "nodejs": ["node", "nodejs", "node js", "node.js"],
    "nestjs": ["nestjs", "nest.js", "nest js"],
    "nextjs": ["nextjs", "next.js", "next js"],
    "react": ["reactjs", "react.js", "react js"],
    "reactjs": ["react", "react.js"],
    "vuejs": ["vue", "vue.js", "vuejs"],
    "angular": ["angularjs", "angular.js"],
    "expressjs": ["express", "express.js", "expressjs"],
    "express": ["express.js", "expressjs"],
    "mongodb": ["mongo", "mongo db", "mongodb atlas"],
    "postgresql": ["postgres", "postgre", "postgre sql", "psql"],
    "postgres": ["postgresql"],
    "mysql": ["my sql"],
    "sql": ["mysql", "postgresql", "postgres", "sql server", "mssql", "sqlite", "mariadb", "t-sql"],
    "nosql": ["mongodb", "mongo", "dynamodb", "cassandra", "couchdb", "firestore"],
    "javascript": ["js", "es6", "ecmascript"],
    "typescript": ["ts"],
    "git": ["github", "gitlab", "bitbucket"],
    "github": ["git"],
    "restapi": ["rest api", "rest apis", "restful", "restful api", "restful apis", "rest-api", "rest services"],
    "restapis": ["rest api", "restful", "restful api", "restful apis"],
    "jwt": ["json web token", "json web tokens"],
    "rbac": ["role based access", "role-based access", "role based access control", "roles and permissions"],
    "authentication": ["auth", "jwt", "oauth", "login"],
    "cicd": ["ci/cd", "ci cd", "github actions", "gitlab ci", "jenkins", "circleci", "pipelines"],
    "kubernetes": ["k8s"],
    "reduxtoolkit": ["redux toolkit", "rtk", "redux"],
    "redux": ["redux toolkit", "rtk"],
    "reactquery": ["react query", "tanstack query", "tanstack"],
    "tailwindcss": ["tailwind", "tailwind css", "tailwindcss"],
    "tailwind": ["tailwind css", "tailwindcss"],
    "html": ["html5"],
    "html5": ["html"],
    "css": ["css3"],
    "css3": ["css"],
    "aws": ["amazon web services", "ec2", "s3", "eks", "lambda"],
    "reacttestinglibrary": ["react testing library", "testing library", "rtl"],
    "graphql": ["graph ql", "apollo"],
    "docker": ["docker compose", "dockerfile", "containers"],
    "microservices": ["micro services", "micro-services"],
    "websockets": ["websocket", "socket.io", "socketio"],
}

# Skill names that are also normal English words ("rest", "next", "go"...).
# The app never searches for the word itself, only for these safe forms of it.
RISKY_WORDS = {
    "rest": ["rest api", "rest apis", "restful", "rest-api"],
    "next": ["next.js", "nextjs", "next js"],
    "nest": ["nestjs", "nest.js", "nest js"],
    "go": ["golang", "go lang"],
    "express": ["express.js", "expressjs", "express js", "node/express", "node express", "express framework"],
    "login": [],
    "containers": [],
    "pipelines": [],
    "auth": ["auth0", "authentication", "authorization"],
    "ts": [],
    "js": [],
    "apollo": ["apollo client", "apollo server"],
    "s3": ["aws s3", "amazon s3"],
    "lambda": ["aws lambda"],
}

# Words removed from a skill name before searching ("Strong TypeScript knowledge" -> "typescript").
FILLER_WORDS = {"design", "development", "experience", "knowledge", "workflow", "skills", "framework",
                "basics", "programming", "language", "strong", "modern", "proficiency", "hands-on",
                "scripting", "publishing", "deployment", "app", "apps"}

# Short forms of degree fields written on CVs ("BSCS" = a bachelor's in computer science).
DEGREE_FIELD_ALIASES = {
    "computer science": ["bs cs", "bscs", "bs(cs)", "bs-cs", "ms cs", "mscs", "bcs", "mcs", "b.sc computer science"],
    "software engineering": ["bs se", "bsse", "bs(se)", "bs-se", "ms se", "msse"],
    "information technology": ["bs it", "bsit", "bs(it)", "bs-it", "ms it", "msit"],
    "computer engineering": ["bs ce", "bsce", "computer systems engineering"],
    "business administration": ["bba", "mba"],
}

# Numbers written as words in job descriptions ("five years of experience").
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15}
