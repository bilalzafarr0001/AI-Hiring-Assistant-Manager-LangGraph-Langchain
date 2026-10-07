-- Demo data so you can try the app. Change or remove for real use.

INSERT INTO departments (name) VALUES
    ('Frontend Engineering'),
    ('Backend Engineering'),
    ('Mobile Engineering')
ON CONFLICT (name) DO NOTHING;

INSERT INTO users (full_name, email, role, department_id) VALUES
    ('Ayesha Khan (Recruiter)',   'hr@bilal.local',           'RECRUITER',   NULL),
    ('Usman Ali (HOD Frontend)',  'hod.frontend@bilal.local', 'HOD',         (SELECT id FROM departments WHERE name = 'Frontend Engineering')),
    ('Sara Ahmed (HOD Backend)',  'hod.backend@bilal.local',  'HOD',         (SELECT id FROM departments WHERE name = 'Backend Engineering')),
    ('Hamza Tariq (Frontend)',    'hamza@bilal.local',        'INTERVIEWER', (SELECT id FROM departments WHERE name = 'Frontend Engineering')),
    ('Hina Raza (Frontend)',      'hina@bilal.local',         'INTERVIEWER', (SELECT id FROM departments WHERE name = 'Frontend Engineering')),
    ('Ali Hassan (Backend)',      'ali@bilal.local',          'INTERVIEWER', (SELECT id FROM departments WHERE name = 'Backend Engineering'))
ON CONFLICT (email) DO NOTHING;
