// Deliberately small functional smoke test, not a representative customer design.
module mac(input logic clk, input logic [31:0] a, b,
           input logic [63:0] acc, output logic [63:0] result);
  always_ff @(posedge clk) result <= (64'(a) * 64'(b)) + acc;
endmodule

