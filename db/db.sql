DROP TABLE buchung;
DROP TABLE tennisplatz;
DROP TABLE wartungsarbeiter;
DROP TABLE nutzer; 


CREATE TABLE nutzer (
    nid INT AUTO_INCREMENT PRIMARY KEY,
    vorname VARCHAR(250),
    nachname VARCHAR(250),
    geburtsdatum DATE,
    email VARCHAR(100)
);

CREATE TABLE wartungsarbeiter (
    wid INT AUTO_INCREMENT PRIMARY KEY,
    vorname VARCHAR(250),
    nachname VARCHAR(250),
    geburtsdatum DATE
);

CREATE TABLE tennisplatz (
    tid INT AUTO_INCREMENT PRIMARY KEY,
    tennisanlage VARCHAR(250),
    platznummer INT,
    belag VARCHAR(50),
    wid INT NOT NULL,
    datum_der_wartung DATE,
    FOREIGN KEY (wid) REFERENCES wartungsarbeiter(wid)
);

CREATE TABLE buchung (
    buchungsnummer INT AUTO_INCREMENT PRIMARY KEY,
    nid INT NOT NULL,
    tid INT NOT NULL,
    spieldatum DATE,
    spielbeginn TIME,
    spielende TIME,
    FOREIGN KEY (nid) REFERENCES nutzer(nid),
    FOREIGN KEY (tid) REFERENCES tennisplatz(tid)
);

INSERT INTO nutzer (vorname, nachname, geburtsdatum, email) VALUES
('Max', 'Müller', '2000-01-01', 'max.mueller@email.ch'),
('Anna', 'Schwarz', '1999-12-12', 'anna.schwarz@email.ch');

INSERT INTO wartungsarbeiter (vorname, nachname, geburtsdatum) VALUES
('Sonja', 'Sonne', '1985-02-28'),
('Anton', 'Alt', '1965-05-07'),
('Martin', 'Meier', '1992-10-01');

INSERT INTO tennisplatz (tennisanlage, platznummer, belag, wid, datum_der_wartung) VALUES
('Tennis Club Klauberg', 1, 'hart', 1, '2025-11-10'),
('Tennis Club Klauberg', 2, 'hart', 1, '2025-11-10'),
('Tennis Club Klauberg', 3, 'hart', 1, '2025-11-10'),
('Tennis Club Klauberg', 4, 'hart', 1, '2025-11-10'),
('Tanner Tennisclub', 2, 'Sand', 2, '2025-11-10');

INSERT INTO buchung (nid, tid, spieldatum, spielbeginn, spielende) VALUES
(1, 1, '2025-12-16', '14:00:00', '15:00:00'),
(2, 5, '2025-12-18', '12:00:00', '13:00:00');