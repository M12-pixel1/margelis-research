# MARGELIS Native OS: nuo žmogaus sprendimo iki patikrinto agento rezultato

Viešo darbinio teksto projektas | v0.1 | 2026-10-29 | Rūpestėlis Holding

DI agentas gali pasakyti „atlikta“, nors prašytas rezultatas nepasiektas. Jis taip pat gali vykdyti anksčiau patvirtintą veiksmą, kai leidimas jau nebegalioja, arba pakartoti operaciją po techninio sutrikimo. Įmonei svarbus ne vien įtikinamas pokalbis: reikia žinoti, kas leido veikti, kokiomis ribomis ir kas patvirtina rezultatą.

MARGELIS Native OS plėtojama kaip bendras agentų veiklos valdymo sluoksnis. Jis jungia žmogaus sprendimą, konkretaus veiksmo įgaliojimą, atskirą vykdytoją ir rezultato įrodymą. Esamos įmonės sistemos išlieka savo duomenų šaltiniais. Šiame projekte OS reiškia įmonės veiklos koordinavimo architektūrą; tai nėra naujas kompiuterio operacinės sistemos branduolys.

## Ką pristatome dabar

Skelbiame architektūros darbinį aprašą ir atkuriamą trijų klaidų scenarijų demonstraciją: nebegaliojantį įgaliojimą, pakartotinį veiksmą ir klaidingą pranešimą apie užbaigimą. Kiekvienas scenarijus pakartotas po du kartus paprastame etaloniniame rinkinyje ir atskiro proceso HTTP/SQLite laboratorijoje.

Kiekviename paleidime apsaugotas etaloninis variantas atitiko visų trijų scenarijų kriterijus. Tyčia nesaugus variantas jų neatitiko. Pirminiai rezultatai ir šaltinio versija pridedami. Kartojimai nepadidina skirtingų scenarijų skaičiaus.

Tai mūsų apibrėžtų etaloninių elgesių demonstracija. Ji neįrodo visos Native OS saugumo ar gyvų paslaugos integracijų veikimo. Bandymuose nenaudoti klientų duomenys, tikri mokėjimai ar skambučiai. Rezultatai nėra palyginimas su konkurentų produktais.

## Ką tai galėtų duoti klientui

Registracijos paslaugoje sistema turėtų atskirti pasiūlytą laiką, perduotą prašymą ir įstaigos patvirtintą registraciją. Įmonės užduotyje ji turėtų parodyti, kokiu įgaliojimu veikė ir kokia patikra patvirtino baigtį. Šio darbinio aprašo ekonominę vertę dar reikės matuoti: kiek užduočių baigiama patikimai, kiek lieka išimčių ir kiek darbuotojo laiko bei pinigų kainuoja vienas patvirtintas rezultatas.

## Kodėl išlaikome originalius šaltinius

Semantinė atmintis gali padėti rasti informaciją pagal prasmę. Tačiau sugeneruota santrauka nepakeičia originalaus dokumento, žmogaus pasakojimo ar galiojančio sprendimo. Mūsų kryptis - išlaikyti ryšį su šaltiniu, jo versija, galiojimu ir prieigos teisėmis. Asmeninė, įmonės ir šeimos paveldo atmintis turi atskiras ribas.

Parengėme 30 sintetinių semantinės atminties scenarijų ir bandymo protokolą. Šis bandymas dar neatliktas; jo pagerėjimo rezultatų neskelbiame.

## Kam skirta publikacija

Kviečiame techninę bendruomenę tikrinti architektūros ribas, pakartoti viešą demonstraciją ir pateikti konkrečius kontrpavyzdžius. Darbinio aprašo paskelbimas leidžia aptarti pažangą kūrimo metu. Produkcinio pasirengimo ir naudos klientui vertinimui reikės atskirų įrodymų.

AI padėjo parengti tekstą ir pakartoti bandymus. Galutinė autoriaus peržiūra neatlikta. Šiam darbiniam tekstui dar nesuteiktas DOI ir nepriskirta pakartotinio naudojimo licencija.
