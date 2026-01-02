DROP TABLE nutzer;
DROP TABLE tennisplatz;
DROP TABLE wartunsarbeiter;
DROP TABLE buchung; 


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
    platznummer VARCHAR(10),
    belag VARCHAR(100),
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
('Max', 'Müller', 01.01.2000, 'max.müller@email.ch'),
('Anna', 'Schwarz', 12.12.1999, 'anna.schwarz@email.ch');

INSERT INTO wartungsarbeiter (vorname, nachname, geburtsdatum) VALUES
('Sonja', 'Sonne', 28.02.1985),
('Anton', 'Alt', 07.05.1965),
('Martin', 'Meier', 01.10.1992);

INSERT INTO tennisplatz (tennisanlage, platznummer, belag, wid, datum_der_wartung) VALUES
('Tennis Club Klauberg', 1, 'hart', 1, '10.11.2025').
('Tennis Club Klauberg', 2, 'hart', 1, '10.11.2025'),
('Tennis Club Klauberg', 3, 'hart', 1, '10.11.2025'),
('Tennis Club Klauberg', 4, 'hart', 1, '10.11.2025'),
('Tanner Tennisclub', 2, 'Sand', 2, '10.11.2025');

INSERT INTO buchung (nid, tid, spieldatum, spielbeginn, spielende);
(1, 1, 16.12.2025, 14:00, 15:00),
(2, 5, 18., 12:00, 13:00);
