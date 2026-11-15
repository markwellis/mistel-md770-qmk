import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import java.io.File;
import java.io.PrintWriter;

public class ExportTraceIndex extends GhidraScript {
    public void run() throws Exception {
        File directory = new File(getScriptArgs()[0]);
        String name = currentProgram.getName();
        try (PrintWriter functions = new PrintWriter(new File(directory, name + ".functions.tsv"));
             PrintWriter assembly = new PrintWriter(new File(directory, name + ".assembly.tsv"));
             PrintWriter references = new PrintWriter(new File(directory, name + ".references.tsv"))) {
            for (Function function : currentProgram.getFunctionManager().getFunctions(true)) {
                functions.printf("%s\t%s\t%s%n", function.getEntryPoint(),
                    function.getBody().getMaxAddress(), function.getName());
            }
            for (Instruction instruction : currentProgram.getListing().getInstructions(true)) {
                Function function = getFunctionContaining(instruction.getAddress());
                String owner = function == null ? "" : function.getEntryPoint().toString();
                assembly.printf("%s\t%s\t%s%n", instruction.getAddress(), owner, instruction);
                for (Reference reference : instruction.getReferencesFrom()) {
                    references.printf("%s\t%s\t%s\t%s%n", instruction.getAddress(),
                        owner, reference.getToAddress(), reference.getReferenceType());
                }
            }
        }
    }
}
